"""
routes/credentials.py
=====================
Módulo de credenciamento: registro público, validação e checkin.
"""
import logging
import secrets
import threading
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_secretaria
from app.db.models import Credential, RegistrationPayment, User
from app.db.session import get_db
from app.services import email_service
from app.api.routes.modality_mapper import map_ticket_to_slug

router = APIRouter(prefix="/credentials", tags=["Credenciais"])


def recalculate_payment_mismatch(credential: Credential, db: Session) -> bool:
    """Recalcula se há mismatch entre modalidades inscritas e pagas."""
    if not credential.modalities:
        return False
    
    # Buscar todos os pagamentos associados à credencial
    filters = []
    if credential.cpf:
        filters.append(RegistrationPayment.cpf == credential.cpf)
    if credential.email:
        filters.append(RegistrationPayment.email == credential.email)
    if credential.full_name:
        filters.append(func.lower(RegistrationPayment.full_name) == credential.full_name.lower())
    
    if not filters:
        return False  # Sem forma de vincular pagamentos, não há mismatch
    
    all_payments = db.query(RegistrationPayment).filter(or_(*filters)).all()

    # Agregar todos os slugs pagos
    paid_slugs = list(set(
        slug
        for p in all_payments
        for slug in (p.modalities if p.modalities else ([p.modality_slug] if p.modality_slug and p.modality_slug != "outro" else []))
    ))
    
    # Normalizar modalidades inscritas para slugs e comparar
    inscribed_slugs = list(set(
        map_ticket_to_slug(m) for m in credential.modalities if m
    ))
    unpaid = [m for m in inscribed_slugs if m not in paid_slugs and m != "outro"]
    return len(unpaid) > 0


def is_payment_verified(credential: Credential, db: Session) -> bool:
    """Retorna True se todas as modalidades inscritas foram pagas (ou se não há modalidades inscritas)."""
    if not credential.modalities:
        return False
    filters = []
    if credential.cpf:
        filters.append(RegistrationPayment.cpf == credential.cpf)
    if credential.email:
        filters.append(RegistrationPayment.email == credential.email)
    if credential.full_name:
        filters.append(func.lower(RegistrationPayment.full_name) == credential.full_name.lower())
    if not filters:
        return False
    all_payments = db.query(RegistrationPayment).filter(or_(*filters)).all()
    paid_slugs = list(set(
        slug
        for p in all_payments
        for slug in (p.modalities if p.modalities else ([p.modality_slug] if p.modality_slug and p.modality_slug != "outro" else []))
    ))
    inscribed_slugs = list(set(
        map_ticket_to_slug(m) for m in credential.modalities if m
    ))
    # Se todas as modalidades inscritas estão em paid_slugs, está verificado
    return all(m in paid_slugs and m != "outro" for m in inscribed_slugs)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CredentialRegister(BaseModel):
    full_name: str
    birth_date: Optional[str] = None
    cpf: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    church: Optional[str] = None
    pastor_name: Optional[str] = None
    pastor_phone: Optional[str] = None
    presbytery: Optional[str] = None
    modalities: Optional[List[str]] = None
    teams: Optional[List[str]] = None
    participation_type: Optional[str] = None
    guardian_name: Optional[str] = None
    guardian_phone: Optional[str] = None


class RejectRequest(BaseModel):
    reason: str


class ApprovalRequest(BaseModel):
    approved: bool


class CheckinRequest(BaseModel):
    wristband_type: str  # visitante, atleta, col


def _serialize(c: Credential, db: Session) -> dict:
    return {
        "id": c.id,
        "full_name": c.full_name,
        "birth_date": c.birth_date,
        "cpf": c.cpf,
        "email": c.email,
        "phone": c.phone,
        "city": c.city,
        "church": c.church,
        "pastor_name": c.pastor_name,
        "pastor_phone": c.pastor_phone,
        "presbytery": c.presbytery,
        "guardian_name": c.guardian_name,
        "guardian_phone": c.guardian_phone,
        "is_minor": c.is_minor or False,
        "modalities": c.modalities or [],
        "teams": c.teams or [],
        "participation_type": c.participation_type,
        "status": c.status,
        "rejection_reason": c.rejection_reason,
        "reviewed_by": c.reviewed_by,
        "reviewed_at": c.reviewed_at.isoformat() if c.reviewed_at else None,
        "reviewed_by_name": c.reviewer.name if c.reviewer else None,
        "pastor_approved": c.pastor_approved or False,
        "pastor_approved_at": c.pastor_approved_at.isoformat() if c.pastor_approved_at else None,
        "pastor_approved_by_name": c.pastor_approver.name if c.pastor_approver else None,
        "guardian_approved": c.guardian_approved or False,
        "guardian_approved_at": c.guardian_approved_at.isoformat() if c.guardian_approved_at else None,
        "guardian_approved_by_name": c.guardian_approver.name if c.guardian_approver else None,
        "qr_code": c.qr_code,
        "checked_in": c.checked_in,
        "checked_in_at": c.checked_in_at.isoformat() if c.checked_in_at else None,
        "checked_in_by": c.checked_in_by,
        "checked_in_by_name": c.checkin_user.name if c.checkin_user else None,
        "wristband_type": c.wristband_type,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "payment_verified": is_payment_verified(c, db),
        "payment_modalities": c.payment_modalities or [],
        "payment_mismatch": recalculate_payment_mismatch(c, db),
    }


# ---------------------------------------------------------------------------
# Endpoints públicos
# ---------------------------------------------------------------------------

@router.post("/register", status_code=201)
def register_credential(body: CredentialRegister, db: Session = Depends(get_db)):
    """Registro público de credencial — sem autenticação."""
    if body.cpf:
        cpf_norm = body.cpf.strip()
        existing = db.query(Credential).filter(Credential.cpf == cpf_norm).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"CPF já cadastrado com status: {existing.status}",
            )

    if body.email:
        email_norm = body.email.strip()
        existing_email = db.query(Credential).filter(Credential.email == email_norm).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Este email já possui uma credencial cadastrada.",
            )

    qr = secrets.token_urlsafe(16)
    # Garantir unicidade do QR code (extremamente improvável de colidir, mas seguro)
    while db.query(Credential).filter(Credential.qr_code == qr).first():
        qr = secrets.token_urlsafe(16)

    # Calcular se é menor de 18 anos
    is_minor = False
    if body.birth_date:
        try:
            parts = body.birth_date.split("/")
            if len(parts) == 3:
                from datetime import date
                birth = date(int(parts[2]), int(parts[1]), int(parts[0]))
                today = date.today()
                age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
                is_minor = age < 18
        except Exception:
            pass

    cred = Credential(
        full_name=body.full_name.strip(),
        birth_date=body.birth_date,
        cpf=body.cpf.strip() if body.cpf else None,
        email=body.email.strip() if body.email else None,
        phone=body.phone,
        city=body.city,
        church=body.church,
        pastor_name=body.pastor_name,
        pastor_phone=body.pastor_phone,
        presbytery=body.presbytery,
        guardian_name=body.guardian_name.strip() if body.guardian_name else None,
        guardian_phone=body.guardian_phone,
        is_minor=is_minor,
        modalities=body.modalities or [],
        teams=body.teams or [],
        participation_type=body.participation_type,
        status="pending",
        qr_code=qr,
        checked_in=False,
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)

    # Enviar email de confirmação em background para não atrasar a resposta
    cred_id = cred.id

    def send_email_bg(credential_id: int):
        logger.info(f"Thread de email iniciada para credencial ID: {credential_id}")
        from app.db.session import SessionLocal
        db_bg = SessionLocal()
        try:
            c = db_bg.query(Credential).filter(Credential.id == credential_id).first()
            if c:
                logger.info(f"Credencial encontrada, email: {c.email}")
                result = email_service.send_credential_email(c)
                logger.info(f"Resultado do envio de email: {result}")
            else:
                logger.error(f"Credencial ID {credential_id} não encontrada na thread")
        except Exception as e:
            logger.error(f"Erro na thread de email: {e}")
        finally:
            db_bg.close()

    thread = threading.Thread(target=send_email_bg, args=(cred_id,))
    thread.daemon = True
    thread.start()

    return {"id": cred.id, "full_name": cred.full_name, "status": cred.status, "qr_code": cred.qr_code, "email": cred.email}


@router.get("/check/{cpf}")
def check_cpf(cpf: str, db: Session = Depends(get_db)):
    """Verifica se CPF já tem credencial e busca pagamentos associados."""
    cpf_clean = cpf.strip()
    cred = db.query(Credential).filter(Credential.cpf == cpf_clean).first()

    payments = db.query(RegistrationPayment).filter(RegistrationPayment.cpf == cpf_clean).all()
    paid_slugs = list(set(
        slug
        for p in payments
        for slug in (p.modalities if p.modalities else ([p.modality_slug] if p.modality_slug and p.modality_slug != "outro" else []))
    ))
    from app.api.routes.modality_mapper import slug_to_label
    payment_info = {
        "payment_found": len(payments) > 0,
        "paid_modalities": paid_slugs,
        "paid_modalities_labels": [slug_to_label(s) for s in paid_slugs],
        "tickets": [p.ticket_name for p in payments if p.ticket_name],
    }

    if not cred:
        return {"exists": False, "payment_info": payment_info}
    return {
        "exists": True,
        "status": cred.status,
        "full_name": cred.full_name,
        "payment_info": payment_info,
    }


@router.get("/check-email/{email}")
def check_email(email: str, db: Session = Depends(get_db)):
    """Verifica se email já tem credencial cadastrada — endpoint público."""
    email_clean = email.strip()
    cred = db.query(Credential).filter(Credential.email == email_clean).first()

    payments = db.query(RegistrationPayment).filter(RegistrationPayment.email == email_clean).all()
    paid_slugs = list(set(
        slug
        for p in payments
        for slug in (p.modalities if p.modalities else ([p.modality_slug] if p.modality_slug and p.modality_slug != "outro" else []))
    ))
    from app.api.routes.modality_mapper import slug_to_label
    payment_info = {
        "payment_found": len(payments) > 0,
        "paid_modalities": paid_slugs,
        "paid_modalities_labels": [slug_to_label(s) for s in paid_slugs],
        "tickets": [p.ticket_name for p in payments if p.ticket_name],
        "participation_type": payments[0].participation_type if payments else None,
    }

    if not cred:
        return {"exists": False, "status": None, "payment_info": payment_info}
    return {"exists": True, "status": cred.status, "payment_info": payment_info}


@router.get("/qr/{qr_code}")
def get_by_qr(qr_code: str, db: Session = Depends(get_db)):
    """Busca credencial pelo QR code para checkin via câmera."""
    qr_clean = qr_code.strip()
    cred = db.query(Credential).filter(Credential.qr_code == qr_clean).first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credencial não encontrada para o QR Code informado")
    return _serialize(cred, db)


# ---------------------------------------------------------------------------
# Endpoints privados (secretaria)
# ---------------------------------------------------------------------------

@router.get("/stats")
def get_stats(db: Session = Depends(get_db), _=Depends(require_secretaria)):
    """Contadores gerais de credenciamento."""
    total     = db.query(func.count(Credential.id)).scalar()
    pending   = db.query(func.count(Credential.id)).filter(Credential.status == "pending").scalar()
    approved  = db.query(func.count(Credential.id)).filter(Credential.status == "approved").scalar()
    rejected  = db.query(func.count(Credential.id)).filter(Credential.status == "rejected").scalar()
    checked   = db.query(func.count(Credential.id)).filter(Credential.checked_in == True).scalar()
    visitante = db.query(func.count(Credential.id)).filter(Credential.wristband_type == "visitante").scalar()
    atleta    = db.query(func.count(Credential.id)).filter(Credential.wristband_type == "atleta").scalar()
    col       = db.query(func.count(Credential.id)).filter(Credential.wristband_type == "col").scalar()
    return {
        "total": total,
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "checked_in": checked,
        "por_wristband": {"visitante": visitante, "atleta": atleta, "col": col},
    }


@router.get("/")
def list_credentials(
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_secretaria),
):
    """Lista credenciais com filtros."""
    q = db.query(Credential)
    if status_filter:
        q = q.filter(Credential.status == status_filter)
    if search:
        term = f"%{search}%"
        q = q.filter(or_(Credential.full_name.ilike(term), Credential.cpf.ilike(term)))
    creds = q.order_by(Credential.created_at.desc()).all()
    return [_serialize(c, db) for c in creds]


@router.get("/{cred_id}")
def get_credential(cred_id: int, db: Session = Depends(get_db), _=Depends(require_secretaria)):
    cred = db.query(Credential).filter(Credential.id == cred_id).first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credencial não encontrada")
    return _serialize(cred, db)


@router.put("/{cred_id}/approve")
def approve_credential(
    cred_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_secretaria),
):
    cred = db.query(Credential).filter(Credential.id == cred_id).first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credencial não encontrada")
    cred.status = "approved"
    cred.reviewed_by = current_user.id
    cred.reviewed_at = datetime.now(timezone.utc)
    cred.rejection_reason = None
    db.commit()
    db.refresh(cred)

    cred_id = cred.id

    def _send_approval_bg(credential_id: int):
        logger.info(f"Thread de email de aprovação iniciada para credencial ID: {credential_id}")
        from app.db.session import SessionLocal
        db_bg = SessionLocal()
        try:
            c = db_bg.query(Credential).filter(Credential.id == credential_id).first()
            if c:
                result = email_service.send_approval_email(c)
                logger.info(f"Resultado email aprovação: {result}")
            else:
                logger.error(f"Credencial ID {credential_id} não encontrada na thread de aprovação")
        except Exception as e:
            logger.error(f"Erro na thread de email de aprovação: {e}")
        finally:
            db_bg.close()

    t = threading.Thread(target=_send_approval_bg, args=(cred_id,))
    t.daemon = True
    t.start()

    return _serialize(cred, db)


@router.put("/{cred_id}/reject")
def reject_credential(
    cred_id: int,
    body: RejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_secretaria),
):
    cred = db.query(Credential).filter(Credential.id == cred_id).first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credencial não encontrada")
    cred.status = "rejected"
    cred.reviewed_by = current_user.id
    cred.reviewed_at = datetime.now(timezone.utc)
    cred.rejection_reason = body.reason
    db.commit()
    db.refresh(cred)

    cred_id = cred.id

    def _send_rejection_bg(credential_id: int):
        logger.info(f"Thread de email de rejeição iniciada para credencial ID: {credential_id}")
        from app.db.session import SessionLocal
        db_bg = SessionLocal()
        try:
            c = db_bg.query(Credential).filter(Credential.id == credential_id).first()
            if c:
                result = email_service.send_rejection_email(c)
                logger.info(f"Resultado email rejeição: {result}")
            else:
                logger.error(f"Credencial ID {credential_id} não encontrada na thread de rejeição")
        except Exception as e:
            logger.error(f"Erro na thread de email de rejeição: {e}")
        finally:
            db_bg.close()

    t = threading.Thread(target=_send_rejection_bg, args=(cred_id,))
    t.daemon = True
    t.start()

    return _serialize(cred, db)


@router.put("/{cred_id}/revert")
def revert_credential(
    cred_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_secretaria),
):
    """Reverte aprovado/rejeitado de volta para pendente."""
    cred = db.query(Credential).filter(Credential.id == cred_id).first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credencial não encontrada")
    cred.status = "pending"
    cred.reviewed_by = None
    cred.reviewed_at = None
    cred.rejection_reason = None
    db.commit()
    db.refresh(cred)
    return _serialize(cred, db)


@router.put("/{cred_id}/pastor-approve")
def pastor_approve_credential(
    cred_id: int,
    body: ApprovalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_secretaria),
):
    cred = db.query(Credential).filter(Credential.id == cred_id).first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credencial não encontrada")
    cred.pastor_approved = body.approved
    cred.pastor_approved_at = datetime.now(timezone.utc) if body.approved else None
    cred.pastor_approved_by = current_user.id if body.approved else None
    db.commit()
    db.refresh(cred)
    return _serialize(cred, db)


@router.put("/{cred_id}/guardian-approve")
def guardian_approve_credential(
    cred_id: int,
    body: ApprovalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_secretaria),
):
    cred = db.query(Credential).filter(Credential.id == cred_id).first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credencial não encontrada")
    if not cred.is_minor:
        raise HTTPException(status_code=400, detail="Aprovação de responsável só se aplica a menores de idade")
    cred.guardian_approved = body.approved
    cred.guardian_approved_at = datetime.now(timezone.utc) if body.approved else None
    cred.guardian_approved_by = current_user.id if body.approved else None
    db.commit()
    db.refresh(cred)
    return _serialize(cred, db)


@router.put("/{cred_id}/checkin")
def checkin_credential(
    cred_id: int,
    body: CheckinRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_secretaria),
):
    cred = db.query(Credential).filter(Credential.id == cred_id).first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credencial não encontrada")
    cred.checked_in = True
    cred.checked_in_at = datetime.now(timezone.utc)
    cred.checked_in_by = current_user.id
    cred.wristband_type = body.wristband_type
    db.commit()
    db.refresh(cred)
    return _serialize(cred, db)
