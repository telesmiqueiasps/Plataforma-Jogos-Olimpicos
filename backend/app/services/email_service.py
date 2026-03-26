"""
services/email_service.py
=========================
Envio de email transacional via Brevo (Sendinblue).
"""
import logging
import urllib.parse

import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CSS_BASE = """
  body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 0; }
  .container { max-width: 600px; margin: 0 auto; background: white; }
  .header { padding: 30px; text-align: center; }
  .header h1 { color: white; margin: 0; font-size: 24px; }
  .header p { color: rgba(255,255,255,0.8); margin: 8px 0 0; }
  .body { padding: 30px; }
  .greeting { font-size: 18px; font-weight: bold; margin-bottom: 16px; }
  .info-box { border-radius: 8px; padding: 20px; margin: 20px 0; }
  .info-row { display: flex; margin-bottom: 8px; }
  .info-label { font-weight: bold; color: #4a5068; min-width: 140px; }
  .info-value { color: #1a1d2e; }
  .notice { border-left: 4px solid; padding: 12px 16px; border-radius: 4px; margin: 16px 0; font-size: 14px; }
  .qr-section { text-align: center; padding: 24px; background: #f0fdf4; border-radius: 8px; margin: 20px 0; }
  .qr-section h3 { color: #14532d; margin-bottom: 16px; }
  .qr-section img { border: 4px solid #16a34a; border-radius: 8px; padding: 8px; background: white; display: block; margin: 0 auto; }
  .qr-link { margin-top: 12px; font-size: 13px; color: #4a5068; word-break: break-all; }
  .footer { background: #f8f9fc; padding: 20px; text-align: center; color: #8b92a9; font-size: 12px; border-top: 1px solid #e2e6ef; }
"""


def get_qr_url(qr_code_value: str) -> str:
    """Gera URL de QR Code via Google Charts API."""
    checkin_url = f"https://jogossinodal.netlify.app/secretaria.html?qr={qr_code_value}"
    encoded = urllib.parse.quote(checkin_url)
    return f"https://chart.googleapis.com/chart?chs=300x300&cht=qr&chl={encoded}&choe=UTF-8"


def _brevo_send(to_email: str, to_name: str, subject: str, html_content: str) -> bool:
    """Envia um email via Brevo. Retorna True se bem-sucedido."""
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key["api-key"] = settings.BREVO_API_KEY
    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )
    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": to_email, "name": to_name}],
        sender={"email": settings.EMAIL_FROM, "name": settings.EMAIL_FROM_NAME},
        subject=subject,
        html_content=html_content,
    )
    api_instance.send_transac_email(send_smtp_email)
    return True


# ---------------------------------------------------------------------------
# Email 1: Cadastro recebido (sem QR Code)
# ---------------------------------------------------------------------------

def send_credential_email(credential) -> bool:
    """Envia confirmação de recebimento do cadastro. QR Code não incluído —
    será enviado apenas após aprovação."""
    logger.info(f"Iniciando envio de email para: {credential.email}")
    logger.info(f"BREVO_API_KEY configurada: {bool(settings.BREVO_API_KEY)}")
    logger.info(f"EMAIL_FROM: {settings.EMAIL_FROM}")

    if not credential.email or not settings.BREVO_API_KEY:
        return False

    try:
        modalities_text = ", ".join(credential.modalities) if credential.modalities else "Não informado"
        teams_text = ", ".join(credential.teams) if credential.teams else "Não informado"

        html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>{_CSS_BASE}</style></head>
<body>
  <div class="container">
    <div class="header" style="background: linear-gradient(135deg, #1e3a8a, #2563eb);">
      <h1>🏆 Jogos Sinodal PB</h1>
      <p>Credenciamento recebido!</p>
    </div>
    <div class="body">
      <div class="greeting" style="color:#1e3a8a;">Olá, {credential.full_name}! 👋</div>
      <p style="color:#4a5068;">Sua ficha de credenciamento foi recebida com sucesso.
      Abaixo estão os dados que registramos.</p>

      <div class="info-box" style="background:#f8f9fc;">
        <div class="info-row"><span class="info-label">Nome completo:</span><span class="info-value">{credential.full_name}</span></div>
        <div class="info-row"><span class="info-label">Igreja:</span><span class="info-value">{credential.church or 'Não informado'}</span></div>
        <div class="info-row"><span class="info-label">Presbítério:</span><span class="info-value">{credential.presbytery or 'Não informado'}</span></div>
        <div class="info-row"><span class="info-label">Cidade:</span><span class="info-value">{credential.city or 'Não informado'}</span></div>
        <div class="info-row"><span class="info-label">Modalidades:</span><span class="info-value">{modalities_text}</span></div>
        <div class="info-row"><span class="info-label">Equipes:</span><span class="info-value">{teams_text}</span></div>
      </div>

      <div class="notice" style="background:#fef3c7; border-color:#f59e0b; color:#92400e;">
        ⏳ <strong>Sua credencial está aguardando validação da comissão.</strong><br>
        Você receberá um novo email assim que for aprovada ou rejeitada.
      </div>

      <p style="color:#4a5068; font-size:14px;">📬 <strong>Fique atento ao seu email!</strong></p>
    </div>
    <div class="footer">
      <p>Este email foi enviado automaticamente. Por favor não responda.</p>
      <p>Jogos Sinodal PB — Organização de Eventos</p>
    </div>
  </div>
</body>
</html>"""

        result = _brevo_send(
            credential.email,
            credential.full_name,
            "✅ Credencial recebida — Aguardando validação",
            html_content,
        )
        logger.info(f"Email de cadastro enviado com sucesso para: {credential.email}")
        return result

    except ApiException as e:
        logger.error(f"Erro ApiException Brevo: {e}")
        return False
    except Exception as e:
        logger.error(f"Erro geral email: {e}")
        return False


# ---------------------------------------------------------------------------
# Email 2: Aprovação (com QR Code)
# ---------------------------------------------------------------------------

def send_approval_email(credential) -> bool:
    """Envia email de aprovação com QR Code para check-in."""
    logger.info(f"Iniciando envio de email de aprovação para: {credential.email}")

    if not credential.email or not settings.BREVO_API_KEY:
        return False

    try:
        qr_url = get_qr_url(credential.qr_code)
        checkin_link = f"https://jogossinodal.netlify.app/secretaria.html?qr={credential.qr_code}"
        modalities_text = ", ".join(credential.modalities) if credential.modalities else "Não informado"

        html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>{_CSS_BASE}</style></head>
<body>
  <div class="container">
    <div class="header" style="background: linear-gradient(135deg, #14532d, #16a34a);">
      <h1>🎉 Credencial Aprovada!</h1>
      <p>Você está confirmado(a) para o evento</p>
    </div>
    <div class="body">
      <div class="greeting" style="color:#14532d;">Parabéns, {credential.full_name}! 🎊</div>
      <p style="color:#4a5068;">Sua credencial foi <strong>aprovada</strong> pela comissão.
      Você está confirmado(a) para participar dos Jogos Sinodal PB!</p>

      <div class="info-box" style="background:#f0fdf4; border:1px solid #bbf7d0;">
        <div class="info-row"><span class="info-label">Nome:</span><span class="info-value">{credential.full_name}</span></div>
        <div class="info-row"><span class="info-label">Igreja:</span><span class="info-value">{credential.church or 'Não informado'}</span></div>
        <div class="info-row"><span class="info-label">Modalidades:</span><span class="info-value">{modalities_text}</span></div>
      </div>

      <div class="qr-section">
        <h3>🎫 Seu QR Code de Entrada</h3>
        <img src="{qr_url}" width="220" height="220" alt="QR Code de entrada">
        <p style="color:#14532d; font-weight:bold; margin-top:14px;">
          Apresente este QR Code na entrada do evento
        </p>
        <p class="qr-link">
          Ou acesse diretamente:<br>
          <a href="{checkin_link}" style="color:#16a34a;">{checkin_link}</a>
        </p>
      </div>

      <div class="notice" style="background:#fef3c7; border-color:#f59e0b; color:#92400e;">
        ⚠️ <strong>Salve este email!</strong> Você precisará do QR Code no dia do evento.
      </div>
    </div>
    <div class="footer">
      <p>Este email foi enviado automaticamente. Por favor não responda.</p>
      <p>Jogos Sinodal PB — Organização de Eventos</p>
    </div>
  </div>
</body>
</html>"""

        result = _brevo_send(
            credential.email,
            credential.full_name,
            "🎉 Credencial Aprovada — Jogos Sinodais",
            html_content,
        )
        logger.info(f"Email de aprovação enviado com sucesso para: {credential.email}")
        return result

    except ApiException as e:
        logger.error(f"Erro ApiException Brevo (aprovação): {e}")
        return False
    except Exception as e:
        logger.error(f"Erro ao enviar email de aprovação: {e}")
        return False


# ---------------------------------------------------------------------------
# Email 3: Rejeição (com motivo)
# ---------------------------------------------------------------------------

def send_rejection_email(credential) -> bool:
    """Envia email informando rejeição da credencial com o motivo."""
    logger.info(f"Iniciando envio de email de rejeição para: {credential.email}")

    if not credential.email or not settings.BREVO_API_KEY:
        return False

    try:
        reason = credential.rejection_reason or "Não informado"

        html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>{_CSS_BASE}</style></head>
<body>
  <div class="container">
    <div class="header" style="background: linear-gradient(135deg, #7f1d1d, #dc2626);">
      <h1>❌ Credencial não aprovada</h1>
      <p>Informação sobre seu credenciamento</p>
    </div>
    <div class="body">
      <div class="greeting" style="color:#7f1d1d;">Olá, {credential.full_name}</div>
      <p style="color:#4a5068;">Infelizmente sua credencial <strong>não foi aprovada</strong>
      pela comissão organizadora.</p>

      <div class="notice" style="background:#fee2e2; border-color:#dc2626; color:#991b1b;">
        <strong>Motivo:</strong><br>
        {reason}
      </div>

      <p style="color:#4a5068; font-size:14px;">
        Se acredita que houve um engano, entre em contato com a comissão organizadora.
      </p>
    </div>
    <div class="footer">
      <p>Este email foi enviado automaticamente. Por favor não responda.</p>
      <p>Jogos Sinodal PB — Organização de Eventos</p>
    </div>
  </div>
</body>
</html>"""

        result = _brevo_send(
            credential.email,
            credential.full_name,
            "❌ Credencial não aprovada — Jogos Sinodais",
            html_content,
        )
        logger.info(f"Email de rejeição enviado com sucesso para: {credential.email}")
        return result

    except ApiException as e:
        logger.error(f"Erro ApiException Brevo (rejeição): {e}")
        return False
    except Exception as e:
        logger.error(f"Erro ao enviar email de rejeição: {e}")
        return False
