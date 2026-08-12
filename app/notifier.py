import os
import smtplib
import time
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
SMTP_HOST          = os.getenv("SMTP_HOST", "")
SMTP_PORT          = int(os.getenv("SMTP_PORT", 587))
SMTP_USER          = os.getenv("SMTP_USER", "")
SMTP_PASS          = os.getenv("SMTP_PASS", "")
ALERT_EMAIL_TO     = os.getenv("ALERT_EMAIL_TO") or os.getenv("ALERT_TO", "")
CRITICAL_THRESHOLD = int(os.getenv("ALERT_THRESHOLD", 15))
COOLDOWN_HOURS     = int(os.getenv("ALERT_COOLDOWN_HOURS", 24))

_last_alerts = {}

def build_html_digest(items):
    """Construye la plantilla HTML con la tabla de consumibles críticos."""
    rows_html = ""
    for item in items:
        rows_html += f"""
        <tr style="border-top: 1px solid #e5e5ea;">
          <td style="padding: 12px 10px; font-weight: 600; color: #1d1d1f;">
            {item['printer_name']} <br>
            <span style="font-size: 12px; font-weight: normal; color: #86868b;">({item['ip']})</span>
          </td>
          <td style="padding: 12px 10px; color: #515154;">{item['supply_name']}</td>
          <td style="padding: 12px 10px; font-weight: 700; color: #e53e3e; text-align: right; font-size: 16px;">
            {item['display_val']}
          </td>
        </tr>
        """

    return f"""<html>
<head><meta charset="utf-8"></head>
<body style="margin: 0; padding: 0; background-color: #f5f5f7; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
  <div style="background-color: #f5f5f7; padding: 30px 15px;">
    <table border="0" cellpadding="0" cellspacing="0" style="max-width: 600px; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border: 1px solid #e5e5ea; padding: 28px; margin: auto; width: 100%;">
      <tbody>
        <tr>
          <td>
            <div style="text-align: center; margin-bottom: 20px;">
              <h3 style="font-size: 20px; font-weight: 600; color: #1d1d1f; margin: 0;">
                Consumibles en Nivel Crítico ({len(items)})
              </h3>
            </div>

            <p style="font-size: 14px; color: #515154; line-height: 1.5; text-align: center; margin-bottom: 20px;">
              Se han detectado los siguientes consumibles por debajo o cerca del umbral del <strong>{CRITICAL_THRESHOLD}%</strong>:
            </p>

            <div style="background-color: #fbfbfd; border: 1px solid #e5e5ea; border-radius: 8px; padding: 12px; margin-bottom: 24px;">
              <table border="0" cellpadding="0" cellspacing="0" style="width: 100%; border-collapse: collapse; font-size: 13px;">
                <tr style="color: #86868b; text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 700;">
                  <th style="padding: 8px 10px;">Impresora</th>
                  <th style="padding: 8px 10px;">Consumible</th>
                  <th style="padding: 8px 10px; text-align: right;">Nivel</th>
                </tr>
                </thead>
                <tbody>
                  {rows_html}
                </tbody>
              </table>
            </div>

            <div style="background-color: #fff5f5; border: 1px solid #feb2b2; border-radius: 8px; padding: 14px; text-align: center; margin-bottom: 20px;">
              <p style="font-size: 13px; color: #1d1d1f; margin: 0;">
                <strong>Acción recomendada:</strong> Revisar el stock de reposición para los equipos indicados.
              </p>
            </div>

            <hr style="border: none; border-top: 1px solid #e5e5ea; margin: 20px 0 16px 0;">
            <p style="font-size: 12px; color: #86868b; text-align: center; margin: 0;">
              Notificación creada de manera automática a través de <a href="http://192.168.2.51:2026" style="color: #007aff; text-decoration: none; font-weight: 500;">printers-dashboard</a>.
            </p>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</body>
</html>"""


def send_consolidated_email(critical_items):
    """Envía un único correo con la lista de consumibles bajos."""
    if not SMTP_HOST or not ALERT_EMAIL_TO:
        print("[NOTIFIER] Configuración SMTP o destinatario faltante. Omitiendo.")
        return False

    msg = EmailMessage()
    count = len(critical_items)
    msg['Subject'] = f"⚠️ Alerta: {count} consumible(s) en nivel crítico"
    msg['From']    = SMTP_USER if SMTP_USER else "printer-dashboard@local"
    msg['To']      = ALERT_EMAIL_TO

    html_content = build_html_digest(critical_items)
    msg.set_content(f"Alerta: Se han detectado {count} consumibles en nivel crítico.")
    msg.add_alternative(html_content, subtype='html')

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            if SMTP_USER and SMTP_PASS:
                server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        print(f"[NOTIFIER] 📧 Correo consolidado enviado con éxito ({count} ítems).")
        return True
    except Exception as e:
        print(f"[NOTIFIER ERROR] Fallo al enviar correo consolidado: {e}")
        return False


def process_alerts(printers):
    """Revisa todas las impresoras y agrupa las alertas en un solo correo."""
    now = time.time()
    cooldown_seconds = COOLDOWN_HOURS * 3600
    items_to_alert = []

    for printer in printers:
        ip = printer.get("ip", "")
        name = printer.get("name", ip)
        supplies = printer.get("supplies", [])

        for supply in supplies:
            pct = supply.get("pct")
            pages = supply.get("pages")
            supply_name = supply.get("name", "Consumible")

            display_val = None
            if pct is not None and pct <= CRITICAL_THRESHOLD:
                display_val = f"{pct}%"
            elif pages is not None and pages < 100:
                display_val = f"<{pages} pgs"

            if display_val:
                alert_key = f"{ip}_{supply_name}"
                last_sent = _last_alerts.get(alert_key, 0)

                # Verificar cooldown
                if (now - last_sent) >= cooldown_seconds:
                    items_to_alert.append({
                        "printer_name": name,
                        "ip": ip,
                        "supply_name": supply_name,
                        "display_val": display_val,
                        "alert_key": alert_key
                    })

    if items_to_alert:
        print(f"[NOTIFIER] Se encontraron {len(items_to_alert)} ítems críticos para alertar.")
        if send_consolidated_email(items_to_alert):
            # Marcar cooldown solo si el envío fue exitoso
            for item in items_to_alert:
                _last_alerts[item["alert_key"]] = now
    else:
        print("[NOTIFIER] Escaneo completado. No hay alertas nuevas que enviar.")