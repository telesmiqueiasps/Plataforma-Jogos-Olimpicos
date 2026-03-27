"""
routes/webhook.py
=================
Webhook para receber pagamentos do e-inscrições via Pluga.
URL configurada na Pluga: https://sports-platform-api.onrender.com/api/webhooks/einscricoes
"""
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.models import Credential, RegistrationPayment
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def map_ticket_to_slug(ticket_name: str) -> str:
    """Mapeia nome do ingresso do e-inscrições para slug da modalidade."""
    name = ticket_name.lower().strip()
    if "futsal" in name or "futebol" in name:
        return "futsal"
    if "vôlei" in name or "volei" in name or "vólei" in name or "volleyball" in name:
        return "volleyball"
    if "basquete" in name or "basketball" in name or "basquetebol" in name:
        return "basketball"
    if "corrida" in name or "running" in name or "100m" in name or "200m" in name or "rasos" in name:
        return "running"
    if "tênis de mesa" in name or "tenis de mesa" in name or "ping pong" in name or "tênis" in name:
        return "tenis_mesa"
    if "dominó" in name or "domino" in name or "dupla" in name:
        return "domino"
    if "xadrez" in name or "chess" in name:
        return "xadrez"
    if "dama" in name or "checkers" in name:
        return "dama"
    return "outro"


def normalize_cpf(cpf_raw: str) -> str:
    """Remove formatação e retorna CPF com máscara 000.000.000-00."""
    digits = "".join(filter(str.isdigit, str(cpf_raw or "")))
    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    return digits


@router.post("/einscricoes")
@router.post("/einscrições")
async def receive_einscricoes_payment(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Recebe webhook do e-inscrições via Pluga.

    JSON esperado:
    {
        "id": 250,
        "name": "Nome Completo",
        "email": "email@exemplo.com",
        "phone": "83999999999",
        "order_id": 1,
        "order_status": "Ok",
        "ticket_name": "Futsal Masculino [Quadra 01]",
        "ticket_sale_price": "20.00",
        "first_name": "Nome",
        "last_name": "Sobrenome",
        "event_name": "Jogos Sinodais"
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

    full_name = body.get("name") or f"{body.get('first_name', '')} {body.get('last_name', '')}".strip()
    email = body.get("email", "")
    phone = body.get("phone", "")
    ticket_name = body.get("ticket_name", "")
    order_id = str(body.get("order_id") or body.get("id") or "")

    cpf_raw = (
        body.get("cpf")
        or body.get("document")
        or body.get("tax_id")
        or body.get("cpf_cnpj")
        or ""
    )
    cpf = normalize_cpf(cpf_raw) if cpf_raw else None

    modality_slug = map_ticket_to_slug(ticket_name) if ticket_name else "outro"

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
        modality_slug=modality_slug,
        amount_paid=amount,
        order_id=order_id,
        order_status=order_status,
        raw_data=body,
    )
    db.add(payment)
    db.commit()
    logger.info(f"Pagamento salvo: {full_name} - {ticket_name} → {modality_slug}")

    # Vincular com credencial existente (por CPF ou email)
    credential = None
    if cpf:
        credential = db.query(Credential).filter(Credential.cpf == cpf).first()
    if not credential and email:
        credential = db.query(Credential).filter(Credential.email == email).first()

    if credential:
        filter_field = Credential.cpf == cpf if cpf else Credential.email == email
        all_payments = db.query(RegistrationPayment).filter(filter_field).all()

        paid_slugs = list(set(p.modality_slug for p in all_payments if p.modality_slug != "outro"))
        credential.payment_verified = True
        credential.payment_modalities = paid_slugs

        cred_mods = credential.modalities or []
        unpaid = [m for m in cred_mods if m not in paid_slugs]
        credential.payment_mismatch = len(unpaid) > 0

        db.commit()
        logger.info(f"Credencial atualizada: {credential.full_name} - pagas: {paid_slugs}")

    return {
        "status": "ok",
        "participant": full_name,
        "ticket": ticket_name,
        "modality": modality_slug,
        "credential_linked": credential is not None,
    }


@router.get("/test")
async def test_webhook():
    return {"status": "webhook ativo", "url": "/api/webhooks/einscricoes"}


@router.get("/payments")
async def list_payments(db: Session = Depends(get_db)):
    """Lista pagamentos recebidos — para debug e verificação."""
    payments = (
        db.query(RegistrationPayment)
        .order_by(RegistrationPayment.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": p.id,
            "name": p.full_name,
            "cpf": p.cpf,
            "email": p.email,
            "ticket": p.ticket_name,
            "modality": p.modality_slug,
            "amount": float(p.amount_paid or 0),
            "order_id": p.order_id,
            "order_status": p.order_status,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in payments
    ]
