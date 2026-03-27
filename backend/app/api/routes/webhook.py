"""
routes/webhook.py
=================
Webhook para receber pagamentos do e-inscrições via Pluga.
URL configurada na Pluga: https://sports-platform-api.onrender.com/api/webhooks/einscricoes
"""
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Credential, RegistrationPayment
from app.db.session import get_db
from app.api.routes.credentials import recalculate_payment_mismatch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def map_ticket_to_slug(ticket_name: str) -> str:
    """Mapeia nome do ingresso/modalidade do e-inscrições para slug da modalidade."""
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


def extract_modalities(body: dict) -> list:
    """Extrai modalidades dos campos específicos do e-inscrições."""
    modality_fields = [
        "modalidade_01_7963068",
        "modalidade_02_7963115",
        "modalidade_03_7963116",
        "modalidade_04_7963117",
    ]

    slugs = []
    for field in modality_fields:
        value = body.get(field, "")
        if value and str(value).strip() and str(value).lower() not in ("", "exemplo", "none", "null"):
            slug = map_ticket_to_slug(str(value))
            if slug and slug != "outro" and slug not in slugs:
                slugs.append(slug)

    # Também tentar pelo ticket_name
    ticket = body.get("ticket_name", "")
    if ticket and str(ticket).lower() not in ("normal", "padrão", "exemplo", ""):
        slug = map_ticket_to_slug(str(ticket))
        if slug and slug != "outro" and slug not in slugs:
            slugs.append(slug)

    return slugs


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
    email = body.get("email", "").strip() or None
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
    cpf_raw = (
        body.get("cpf")
        or body.get("document")
        or body.get("tax_id")
        or body.get("cpf_cnpj")
        or ""
    )
    cpf = normalize_cpf(cpf_raw) if cpf_raw else None

    # Modalidades via campos específicos
    modalities = extract_modalities(body)
    # Salva o primeiro slug para compatibilidade com campo único
    modality_slug = modalities[0] if modalities else (map_ticket_to_slug(ticket_name) if ticket_name else "outro")

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
        credential = db.query(Credential).filter(Credential.email == email).first()
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
            "phone": p.phone,
            "ticket": p.ticket_name,
            "ticket_number": p.ticket_number,
            "modality": p.modality_slug,
            "amount": float(p.amount_paid or 0),
            "order_id": p.order_id,
            "order_status": p.order_status,
            "church": p.church,
            "pastor_name": p.pastor_name,
            "pastor_phone": p.pastor_phone,
            "presbytery": p.presbytery,
            "participation_type": p.participation_type,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in payments
    ]
