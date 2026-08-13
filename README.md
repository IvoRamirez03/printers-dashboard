# Monitor de Impresoras — Dashboard SNMP & IPP

Dashboard web para monitorizar niveles de tinta/tóner vía SNMP e IPP en tiempo real, con alertas consolidadas por correo electrónico.

Python + Flask + Docker. Puerto: **http://localhost:2026**

## Requisitos

- Docker Desktop (Mac/Windows) o Docker Engine (Linux)
- Acceso de red a las impresoras (192.168.2.19–192.168.2.39)
- Cuenta/Servidor SMTP para el envío de alertas por correo electrónico (ej. Gmail, Mailtrap, SendGrid)

## Configuración (`.env`)

Crea un archivo `.env` en la raíz del proyecto (al mismo nivel que `docker-compose.yml`) basándote en la siguiente plantilla:

```ini
# Configuración del Sistema e Impresoras
TZ=Europe/Madrid
IP_START=19
IP_END=39
SNMP_COMMUNITY=public
POLL_INTERVAL=120

# Configuración de Alertas por Correo (SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu_correo@gmail.com
SMTP_PASS=tu_app_password_de_16_caracteres
ALERT_EMAIL_TO=administrador@tuempresa.com
ALERT_THRESHOLD=15
ALERT_COOLDOWN_HOURS=24