"""
routes/webhook.py
=================
Webhook para receber pagamentos do e-inscrições via Pluga.
URL configurada na Pluga: https://sports-platform-api.onrender.com/api/webhooks/einscricoes
"""
import logging

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db.models import Credential, ModalityMapping, RegistrationPayment
from app.db.session import get_db
from app.api.deps import require_secretaria
from app.api.routes.credentials import recalculate_payment_mismatch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def normalize_cpf(cpf_raw: str) -> str:
    """Remove formatação e retorna CPF com máscara 000.000.000-00."""
    digits = "".join(filter(str.isdigit, str(cpf_raw or "")))
    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    return digits


def _normalize_for_mapping(s: str) -> str:
    """Remove conteúdo entre colchetes/parênteses, acentos e espaços extras."""
    import re, unicodedata
    s = re.sub(r'\[.*?\]', '', s)
    s = re.sub(r'\(.*?\)', '', s)
    s = s.lower().strip()
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ' '.join(s.split())


def map_ticket_to_slug_db(ticket_name: str, db: Session) -> str:
    """
    Mapeia nome do ingresso para slug buscando na tabela modality_mappings.
    Usa keyword mais longa (mais específica) primeiro.
    """
    if not ticket_name:
        return None
    normalized = _normalize_for_mapping(ticket_name)
    mappings = db.query(ModalityMapping).filter(ModalityMapping.active == True).all()
    mappings.sort(key=lambda m: len(m.keyword), reverse=True)
    for mapping in mappings:
        kw = _normalize_for_mapping(mapping.keyword)
        if kw and kw in normalized:
            return mapping.sport_slug
    return None


def extract_modalities(body: dict, db: Session) -> tuple:
    """
    Extrai e mapeia modalidades dos campos do e-inscrições.
    Campos: modalidade_01_7963068 até modalidade_04_7963117
    Valor exemplo: "Futsal Masculino [Quadra 01] (R$ 20,00)"

    Retorna (slugs, raw_names).
    """
    modality_fields = [
        "modalidade_01_7963068",
        "modalidade_02_7963115",
        "modalidade_03_7963116",
        "modalidade_04_7963117",
    ]

    slugs = []
    raw_names = []

    for field in modality_fields:
        value = str(body.get(field, "") or "").strip()
        if not value or value.lower() in ("exemplo", "none", "null", "-", "n/a"):
            continue

        raw_names.append(value)
        slug = map_ticket_to_slug_db(value, db)

        if slug and slug not in slugs:
            slugs.append(slug)
            logger.info(f"Modalidade mapeada: '{value}' → '{slug}'")
        elif not slug:
            logger.warning(f"Modalidade NÃO mapeada: '{value}'")

    # Também tentar pelo ticket_name (fallback)
    ticket = str(body.get("ticket_name", "") or "").strip()
    if ticket and ticket.lower() not in ("normal", "padrão", "exemplo", "none", "null", ""):
        slug = map_ticket_to_slug_db(ticket, db)
        if slug and slug not in slugs:
            slugs.append(slug)
            logger.info(f"Modalidade mapeada via ticket_name: '{ticket}' → '{slug}'")

    return slugs, raw_names


def map_participation_type(raw: str) -> str:
    """Normaliza tipo de participação para os valores internos."""
    if not raw:
        return ""
    val = raw.strip().lower()
    if val in ("atleta", "athlete"):
        return "atleta"
    if val in ("visitante", "visitor"):
        return "visitante"
    if val in ("col", "colaborador", "staff"):
        return "col"
    return raw.strip()


@router.post("/einscricoes")
@router.post("/einscrições")
async def receive_einscricoes_payment(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Recebe webhook do e-inscrições via Pluga.

    JSON esperado (campos principais):
    {
        "name": "Nome Completo",
        "first_name": "Nome",
        "last_name": "Sobrenome",
        "email": "email@exemplo.com",
        "phone": "83999999999",
        "order_id": 1,
        "order_status": "Ok",
        "ticket_name": "Normal",
        "ticket_sale_price": "20.00",
        "ticket_number": "ABC-001",
        "modalidade_01_7963068": "Futsal Masculino",
        "modalidade_02_7963115": "Vôlei",
        "modalidade_03_7963116": "",
        "modalidade_04_7963117": "",
        "igreja_que_congrega_7933060": "Igreja XYZ",
        "nome_do_seu_pastor_7933061": "Pastor João",
        "numero_whatsapp_do_seu_pastor_7933059": "83988888888",
        "faz_parte_de_qual_federacao_presbiterio_7933057": "Presbitério ABC",
        "tipo_de_inscricao_7933056": "Atleta"
    }
    """
    try:
        body = await request.json()
        logger.info(f"Webhook recebido: {body}")
    except Exception as e:
        logger.error(f"Erro ao parsear webhook: {e}")
        return {"status": "error", "reason": "JSON inválido"}

    order_status = str(body.get("order_status", "")).lower()
    if order_status not in ("ok", "aprovado", "approved", "paid", "confirmed", ""):
        logger.info(f"Ignorando webhook com status: {order_status}")
        return {"status": "ignored", "reason": f"Status não aprovado: {order_status}"}

    first_name = body.get("first_name", "")
    last_name = body.get("last_name", "")
    full_name = (body.get("name") or f"{first_name} {last_name}").strip()
    email = body.get("email", "").lower().strip() or None
    phone = body.get("phone", "")
    ticket_name = body.get("ticket_name", "")
    ticket_number = body.get("ticket_number", "") or body.get("ticket_code", "")
    order_id = str(body.get("order_id") or body.get("id") or "")

    # Campos eclesiásticos/perfil
    church           = body.get("igreja_que_congrega_7933060", "") or None
    pastor_name      = body.get("nome_do_seu_pastor_7933061", "") or None
    pastor_phone     = body.get("numero_whatsapp_do_seu_pastor_7933059", "") or None
    presbytery       = body.get("faz_parte_de_qual_federacao_presbiterio_7933057", "") or None
    participation_type = map_participation_type(
        body.get("tipo_de_inscricao_7933056", "") or ""
    ) or None

    # CPF (pode ou não vir no webhook)
    # Tentar campos fixos primeiro; depois varrer campos customizados do e-inscrições
    cpf_raw = (
        body.get("cpf")
        or body.get("document")
        or body.get("tax_id")
        or body.get("cpf_cnpj")
        or next(
            (str(v) for k, v in body.items() if k.startswith("numero_do_documento") and v),
            ""
        )
        or ""
    )
    cpf = normalize_cpf(cpf_raw) if cpf_raw else None
    if not cpf:
        logger.warning(f"CPF não encontrado no webhook para: {full_name} ({email})")

    # Modalidades via campos específicos
    modalities, raw_modality_names = extract_modalities(body, db)
    # Salva o primeiro slug para compatibilidade com campo único
    modality_slug = modalities[0] if modalities else None
    # ticket_name: preferir nomes originais das modalidades para rastreabilidade
    ticket_name = ", ".join(raw_modality_names) if raw_modality_names else ticket_name

    price_raw = body.get("ticket_sale_price") or body.get("price") or body.get("amount") or "0"
    try:
        amount = float(str(price_raw).replace(",", ".").replace("R$", "").strip())
    except Exception:
        amount = 0.0

    payment = RegistrationPayment(
        cpf=cpf,
        full_name=full_name,
        email=email,
        phone=phone,
        ticket_name=ticket_name,
        ticket_number=ticket_number or None,
        modality_slug=modality_slug,
        modalities=modalities if modalities else None,
        amount_paid=amount,
        order_id=order_id,
        order_status=order_status,
        church=church,
        pastor_name=pastor_name,
        pastor_phone=pastor_phone,
        presbytery=presbytery,
        participation_type=participation_type,
        raw_data=body,
    )
    db.add(payment)
    db.commit()
    logger.info(f"Pagamento salvo: {full_name} - {ticket_name} → {modalities}")

    # Vincular com credencial existente: CPF → email → nome
    credential = None
    link_method = None
    if cpf:
        credential = db.query(Credential).filter(Credential.cpf == cpf).first()
        if credential:
            link_method = f"CPF: {cpf}"
    if not credential and email:
        credential = db.query(Credential).filter(func.lower(Credential.email) == email).first()
        if credential:
            link_method = f"email: {email}"
            logger.info(f"Credencial vinculada por email: {email}")
    if not credential and full_name:
        credential = (
            db.query(Credential)
            .filter(func.lower(Credential.full_name) == full_name.lower())
            .first()
        )
        if credential:
            link_method = f"nome: {full_name}"

    if credential:
        # Atualizar dados eclesiásticos se ausentes na credencial
        if church and not credential.church:
            credential.church = church
        if pastor_name and not credential.pastor_name:
            credential.pastor_name = pastor_name
        if pastor_phone and not credential.pastor_phone:
            credential.pastor_phone = pastor_phone
        if presbytery and not credential.presbytery:
            credential.presbytery = presbytery

        # Recalcular payment_verified e mismatch com todos os pagamentos do participante
        filter_field = (
            Credential.cpf == cpf if cpf
            else Credential.email == email if email
            else Credential.full_name == full_name
        )
        all_payments = db.query(RegistrationPayment).filter(
            (RegistrationPayment.cpf == cpf) if cpf
            else (RegistrationPayment.email == email) if email
            else (RegistrationPayment.full_name == full_name)
        ).all()

        # Agregar todos os slugs pagos de todos os pagamentos
        paid_slugs = list(set(
            slug
            for p in all_payments
            for slug in (p.modalities if p.modalities else ([p.modality_slug] if p.modality_slug and p.modality_slug != "outro" else []))
        ))
        credential.payment_verified = True
        credential.payment_modalities = paid_slugs

        # Recalcular mismatch baseado no estado atual
        credential.payment_mismatch = recalculate_payment_mismatch(credential, db)

        db.commit()
        logger.info(f"Credencial atualizada via {link_method}: {credential.full_name} - pagas: {paid_slugs}")

    return {
        "status": "ok",
        "participant": full_name,
        "email": email,
        "modalities": modalities,
        "church": church,
        "credential_linked": credential is not None,
        "credential_id": credential.id if credential else None,
    }


@router.get("/test")
async def test_webhook():
    return {"status": "webhook ativo", "url": "/api/webhooks/einscricoes"}


@router.get("/payments")
async def list_payments(
    search: Optional[str] = Query(None),
    participation_type: Optional[str] = Query(None),
    modality: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_secretaria),
):
    """Lista pagamentos recebidos com filtros — requer autenticação de secretaria."""
    q = db.query(RegistrationPayment)

    if search:
        term = f"%{search}%"
        q = q.filter(or_(
            RegistrationPayment.full_name.ilike(term),
            RegistrationPayment.email.ilike(term),
        ))
    if participation_type:
        q = q.filter(func.lower(RegistrationPayment.participation_type) == participation_type.lower())
    if modality:
        q = q.filter(
            or_(
                RegistrationPayment.modality_slug == modality,
                RegistrationPayment.modalities.contains([modality]),
            )
        )

    payments = q.order_by(RegistrationPayment.created_at.desc()).all()

    # Buscar credenciais vinculadas por email (LEFT JOIN via Python)
    emails = [p.email for p in payments if p.email]
    creds_by_email: dict = {}
    if emails:
        creds = db.query(Credential).filter(
            func.lower(Credential.email).in_([e.lower() for e in emails])
        ).all()
        for c in creds:
            if c.email:
                creds_by_email[c.email.lower()] = c

    result = []
    for p in payments:
        cred = creds_by_email.get(p.email.lower()) if p.email else None
        result.append({
            "id": p.id,
            "name": p.full_name,
            "cpf": p.cpf,
            "email": p.email,
            "phone": p.phone,
            "ticket": p.ticket_name,
            "ticket_number": p.ticket_number,
            "modality": p.modality_slug,
            "modalities": p.modalities or ([p.modality_slug] if p.modality_slug else []),
            "amount": float(p.amount_paid or 0),
            "order_id": p.order_id,
            "order_status": p.order_status,
            "church": p.church,
            "pastor_name": p.pastor_name,
            "pastor_phone": p.pastor_phone,
            "presbytery": p.presbytery,
            "participation_type": p.participation_type,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "credential_id": cred.id if cred else None,
            "credential_status": cred.status if cred else None,
        })
    return result
