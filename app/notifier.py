import os
import smtplib
import time
from email.message import EmailMessage
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# ---------------------------------------------------------------------------
# Configuración desde Variables de Entorno
# ---------------------------------------------------------------------------
SMTP_HOST          = os.getenv("SMTP_HOST", "")
SMTP_PORT          = int(os.getenv("SMTP_PORT", 587))
SMTP_USER          = os.getenv("SMTP_USER", "")
SMTP_PASS          = os.getenv("SMTP_PASS", "")
ALERT_EMAIL_TO     = os.getenv("ALERT_EMAIL_TO") or os.getenv("ALERT_TO", "")
CRITICAL_THRESHOLD = int(os.getenv("ALERT_THRESHOLD", 15))      # Umbral por defecto: 15%
COOLDOWN_HOURS     = int(os.getenv("ALERT_COOLDOWN_HOURS", 24)) # Horas de espera antes de re-enviar

# Registro en memoria para evitar spam: { "192.168.2.19_Black Toner": timestamp }
_last_alerts = {}

def send_email_alert(printer_name, ip, supply_name, pct):
    """Envía un correo electrónico HTML con el diseño personalizado."""
    if not SMTP_HOST or not ALERT_EMAIL_TO:
        print("[NOTIFIER] Configuración SMTP o correo de destino faltante. Omitiendo envío.")
        return

    msg = EmailMessage()
    msg['Subject'] = f"⚠️ Alerta: {printer_name} - {supply_name} al {pct}%"
    msg['From']    = SMTP_USER if SMTP_USER else "printer-dashboard@local"
    msg['To']      = ALERT_EMAIL_TO

    # Plantilla HTML personalizada
    html_content = f"""<!DOCTYPE html>
<html>

<head>
  <meta charset="utf-8">
</head>

<body style="margin: 0; padding: 0; background-color: #f5f5f7;">
  <div
    style="background-color: #f5f5f7; padding: 40px 15px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; min-height: 100%;">
    <table border="0" cellpadding="0" cellspacing="0"
      style="max-width: 600px; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border: 1px solid #e5e5ea; padding: 32px; margin: auto; width: 100%;">
      <tbody>
        <tr>
          <td>
            <!-- Badge & Header -->
            <div style="text-align: center; margin-bottom: 20px;">
              <span
                style="font-size: 11px; font-weight: 700; color: #e53e3e; text-transform: uppercase; letter-spacing: 1px; background-color: #fff5f5; padding: 6px 12px; border-radius: 20px; border: 1px solid #fed7d7; display: inline-block; margin-bottom: 12px;">
                Alerta del Sistema
              </span>
              <h3 style="font-size: 22px; font-weight: 600; color: #1d1d1f; margin: 0; letter-spacing: -0.4px;">
                Nivel de Consumible Crítico
              </h3>
            </div>

            <!-- Big Stat Display -->
            <div style="text-align: center; margin-top: 16px; margin-bottom: 24px;">
              <p
                style="font-size: 12px; font-weight: 700; color: #86868b; text-transform: uppercase; letter-spacing: 1px; margin: 0 0 4px 0;">
                Nivel Actual Restante
              </p>
              <span style="font-size: 42px; font-weight: 700; color: #e53e3e; letter-spacing: -0.5px;">
                {pct}%
              </span>
            </div>

            <!-- Description -->
            <p style="font-size: 15px; color: #515154; line-height: 1.6; text-align: center; margin-bottom: 24px;">
              Se ha detectado que el nivel de tinta/tóner ha caído por debajo del umbral crítico del
              <strong>{CRITICAL_THRESHOLD}%</strong>.
            </p>

            <!-- Detail Table Card -->
            <div
              style="background-color: #fbfbfd; border: 1px solid #e5e5ea; border-radius: 8px; padding: 20px; margin-bottom: 28px;">
              <table border="0" cellpadding="0" cellspacing="0"
                style="width: 100%; border-collapse: collapse; font-size: 14px;">
                <tr>
                  <td style="padding: 10px 0; color: #86868b; font-weight: 500;">Impresora:</td>
                  <td style="padding: 10px 0; font-weight: 600; color: #1d1d1f; text-align: right;">
                    {printer_name} <span style="font-weight: normal; color: #86868b;">({ip})</span>
                  </td>
                </tr>
                <tr style="border-top: 1px solid #f0f0f2;">
                  <td style="padding: 10px 0; color: #86868b; font-weight: 500;">Consumible:</td>
                  <td style="padding: 10px 0; font-weight: 600; color: #1d1d1f; text-align: right;">
                    {supply_name}
                  </td>
                </tr>
                <tr style="border-top: 1px solid #f0f0f2;">
                  <td style="padding: 10px 0; color: #86868b; font-weight: 500;">Estado:</td>
                  <td style="padding: 10px 0; font-weight: 700; color: #e53e3e; text-align: right;">
                    Sustitución recomendada
                  </td>
                </tr>
              </table>
            </div>

            <!-- Urgent Callout Box -->
            <div
              style="background-color: #fff5f5; border: 1px solid #feb2b2; border-radius: 8px; padding: 16px; margin-bottom: 28px; text-align: center;">
              <p
                style="font-size: 13px; color: #c53030; font-weight: 700; margin: 0 0 4px 0; text-transform: uppercase; letter-spacing: 0.5px;">
                Acción Necesaria
              </p>
              <p style="font-size: 14px; color: #1d1d1f; line-height: 1.4; margin: 0;">
                Por favor, dispón de un recambio o reemplaza el consumible a la mayor brevedad para evitar la
                interrupción del servicio.
              </p>
            </div>

            <!-- Footer -->
            <hr style="border: none; border-top: 1px solid #e5e5ea; margin-top: 24px; margin-bottom: 20px;">
            <p style="font-size: 12px; color: #86868b; text-align: center; line-height: 1.6; margin: 0;">
              Notificación automática enviada desde <strong style="color: #515154;">Printer Dashboard</strong>.
            </p>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</body>

</html>"""

    # Texto alternativo para clientes de correo sin renderizado HTML
    msg.set_content(f"Alerta: {printer_name} ({ip}) tiene el consumible '{supply_name}' al {pct}%.")
    msg.add_alternative(html_content, subtype='html')

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            if SMTP_USER and SMTP_PASS:
                server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        print(f"[NOTIFIER] Email enviado exitosamente para {printer_name} [{supply_name}: {pct}%]")
    except Exception as e:
        print(f"[NOTIFIER ERROR] No se pudo enviar el correo: {e}")


def process_alerts(printers):
    """Revisa los consumibles de las impresoras y envía alertas si aplica."""
    now = time.time()
    cooldown_seconds = COOLDOWN_HOURS * 3600

    for printer in printers:
        ip = printer.get("ip", "")
        name = printer.get("name", ip)
        supplies = printer.get("supplies", [])

        for supply in supplies:
            pct = supply.get("pct")
            supply_name = supply.get("name", "Consumible")

            # Evaluar si el nivel está por debajo o igual al umbral crítico
            if pct is not None and pct <= CRITICAL_THRESHOLD:
                alert_key = f"{ip}_{supply_name}"
                last_sent = _last_alerts.get(alert_key, 0)

                # Comprobar si venció el tiempo de espera (cooldown)
                if (now - last_sent) >= cooldown_seconds:
                    send_email_alert(name, ip, supply_name, pct)
                    _last_alerts[alert_key] = now