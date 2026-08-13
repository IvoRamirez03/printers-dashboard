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
    """Construye la plantilla HTML con la tabla de consumibles bajos."""
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

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin: 0; padding: 0; background-color: #f4f5f7; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
  <div style="background-color: #f4f5f7; padding: 30px 15px;">
    <table border="0" cellpadding="0" cellspacing="0" style="max-width: 580px; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border: 1px solid #e1e4e8; padding: 24px; margin: auto; width: 100%;">
      <tbody>
        <tr>
          <td>
            <!-- Header Compacto de Estado -->
            <table border="0" cellpadding="0" cellspacing="0" style="width: 100%; margin-bottom: 16px;">
              <tr>
                <td style="vertical-align: middle;">
                  <h3 style="font-size: 18px; font-weight: 700; color: #d9381e; margin: 0; display: flex; align-items: center;">
                    Consumibles Bajos ({len(items)})
                  </h3>
                </td>
                <td style="text-align: right; vertical-align: middle;">
                  <span style="font-size: 11px; font-weight: 700; color: #d9381e; background-color: #ffebe9; padding: 4px 8px; border-radius: 4px; border: 1px solid #ffc1c0;">
                    &lt; {CRITICAL_THRESHOLD}%
                  </span>
                </td>
              </tr>
            </table>

            <p style="font-size: 13px; color: #57606a; margin: 0 0 16px 0; line-height: 1.4;">
              Los siguientes dispositivos han alcanzado o superado el umbral bajo de tinta/tóner:
            </p>

            <!-- Tabla de Datos Técnica y Compacta -->
            <div style="border: 1px solid #e1e4e8; border-radius: 6px; overflow: hidden; margin-bottom: 20px;">
              <table border="0" cellpadding="0" cellspacing="0" style="width: 100%; border-collapse: collapse; font-size: 13px;">
                <thead>
                  <tr style="background-color: #f6f8fa; color: #24292f; text-align: left; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #e1e4e8;">
                    <th style="padding: 10px 12px;">Impresora / IP</th>
                    <th style="padding: 10px 12px;">Consumible</th>
                    <th style="padding: 10px 12px; text-align: right;">Nivel</th>
                  </tr>
                </thead>
                <tbody style="font-family: ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace;">
                  {rows_html}
                </tbody>
              </table>
            </div>

            <!-- Botón de Acción Directa (CTA) -->
            <div style="text-align: center; margin-bottom: 20px;">
              <a href="http://192.168.2.51:2026" style="background-color: #0969da; color: #ffffff; padding: 10px 18px; border-radius: 6px; font-weight: 600; font-size: 13px; text-decoration: none; display: inline-block;">
                Abrir Printers Dashboard →
              </a>
            </div>
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
    msg['Subject'] = f"Alerta: {count} consumible(s) en nivel bajo"
    msg['From']    = SMTP_USER if SMTP_USER else "printer-dashboard@local"
    msg['To']      = ALERT_EMAIL_TO

    html_content = build_html_digest(critical_items)
    msg.set_content(f"Alerta: Se han detectado {count} consumibles en nivel bajo.")
    msg.add_alternative(html_content, subtype='html')

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            if SMTP_USER and SMTP_PASS:
                server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        print(f"[NOTIFIER] Correo consolidado enviado con éxito ({count} ítems).")
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
        print(f"[NOTIFIER] Se encontraron {len(items_to_alert)} ítems en nivel bajo para alertar.")
        if send_consolidated_email(items_to_alert):
            # Marcar cooldown solo si el envío fue exitoso
            for item in items_to_alert:
                _last_alerts[item["alert_key"]] = now
    else:
        print("[NOTIFIER] Escaneo completado. No hay alertas nuevas que enviar.")