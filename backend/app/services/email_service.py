"""
services/email_service.py
=========================
Envio de email transacional via Brevo (Sendinblue).
"""
import io
import base64

import qrcode
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

from app.core.config import settings


def generate_qr_base64(qr_code_value: str) -> str:
    """Gera QR Code como imagem PNG base64 para embed no email."""
    url = f"https://jogossinodal.netlify.app/secretaria.html?qr={qr_code_value}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def send_credential_email(credential) -> bool:
    """
    Envia email de confirmação de credencial com QR Code embutido.
    Retorna True se enviado com sucesso, False se falhou ou se faltar email/API key.
    """
    if not credential.email or not settings.BREVO_API_KEY:
        return False

    try:
        qr_b64 = generate_qr_base64(credential.qr_code)

        modalities_text = ", ".join(credential.modalities) if credential.modalities else "Não informado"
        teams_text = ", ".join(credential.teams) if credential.teams else "Não informado"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="UTF-8">
          <style>
            body {{ font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 0; }}
            .container {{ max-width: 600px; margin: 0 auto; background: white; }}
            .header {{ background: linear-gradient(135deg, #1e3a8a, #2563eb); padding: 30px; text-align: center; }}
            .header h1 {{ color: white; margin: 0; font-size: 24px; }}
            .header p {{ color: #bfdbfe; margin: 8px 0 0; }}
            .body {{ padding: 30px; }}
            .greeting {{ font-size: 18px; color: #1e3a8a; font-weight: bold; margin-bottom: 16px; }}
            .info-box {{ background: #f8f9fc; border-radius: 8px; padding: 20px; margin: 20px 0; }}
            .info-row {{ display: flex; margin-bottom: 8px; }}
            .info-label {{ font-weight: bold; color: #4a5068; min-width: 140px; }}
            .info-value {{ color: #1a1d2e; }}
            .qr-section {{ text-align: center; padding: 24px; background: #eff6ff; border-radius: 8px; margin: 20px 0; }}
            .qr-section h3 {{ color: #1e3a8a; margin-bottom: 16px; }}
            .qr-section img {{ border: 4px solid #2563eb; border-radius: 8px; padding: 8px; background: white; }}
            .qr-instruction {{ color: #4a5068; font-size: 14px; margin-top: 12px; }}
            .warning {{ background: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px 16px; border-radius: 4px; margin: 16px 0; font-size: 14px; color: #92400e; }}
            .footer {{ background: #f8f9fc; padding: 20px; text-align: center; color: #8b92a9; font-size: 12px; border-top: 1px solid #e2e6ef; }}
          </style>
        </head>
        <body>
          <div class="container">
            <div class="header">
              <h1>🏆 Jogos Sinodais</h1>
              <p>Credenciamento confirmado!</p>
            </div>
            <div class="body">
              <div class="greeting">Olá, {credential.full_name}! 👋</div>
              <p>Sua ficha de credenciamento foi recebida com sucesso.
              Abaixo estão seus dados e seu QR Code exclusivo para entrada no evento.</p>

              <div class="info-box">
                <div class="info-row">
                  <span class="info-label">Nome completo:</span>
                  <span class="info-value">{credential.full_name}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">Igreja:</span>
                  <span class="info-value">{credential.church or 'Não informado'}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">Presbítério:</span>
                  <span class="info-value">{credential.presbytery or 'Não informado'}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">Cidade:</span>
                  <span class="info-value">{credential.city or 'Não informado'}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">Modalidades:</span>
                  <span class="info-value">{modalities_text}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">Equipes:</span>
                  <span class="info-value">{teams_text}</span>
                </div>
              </div>

              <div class="warning">
                ⏳ <strong>Status atual:</strong> Aguardando validação da comissão.
                Você receberá uma confirmação assim que sua credencial for aprovada.
              </div>

              <div class="qr-section">
                <h3>🎫 Seu QR Code de Entrada</h3>
                <img src="data:image/png;base64,{qr_b64}" width="200" height="200" alt="QR Code">
                <p class="qr-instruction">
                  <strong>Salve este QR Code!</strong><br>
                  Apresente-o na entrada do evento para um credenciamento rápido.<br>
                  Você também pode acessar pelo link no QR Code.
                </p>
              </div>

              <p style="color: #4a5068; font-size: 14px;">
                Se você tiver alguma dúvida, entre em contato com a comissão organizadora.
              </p>
            </div>
            <div class="footer">
              <p>Este email foi enviado automaticamente. Por favor não responda.</p>
              <p>Jogos Sinodais — Organização de Eventos</p>
            </div>
          </div>
        </body>
        </html>
        """

        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key["api-key"] = settings.BREVO_API_KEY
        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(configuration)
        )

        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": credential.email, "name": credential.full_name}],
            sender={"email": settings.EMAIL_FROM, "name": settings.EMAIL_FROM_NAME},
            subject="🏆 Jogos Sinodais — Sua credencial foi recebida!",
            html_content=html_content,
        )

        api_instance.send_transac_email(send_smtp_email)
        return True

    except ApiException as e:
        print(f"Erro ao enviar email Brevo: {e}")
        return False
    except Exception as e:
        print(f"Erro geral no envio de email: {e}")
        return False
