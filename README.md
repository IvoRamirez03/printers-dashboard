# Monitor de Impresoras — Dashboard SNMP

Dashboard web para monitorizar niveles de tinta/tóner via SNMP.
Python + Flask + Docker. Puerto: **http://localhost:2026**

## Requisitos

- Docker Desktop (Mac/Windows) o Docker Engine (Linux)
- Acceso de red a las impresoras (192.168.2.20–192.168.2.37)

## Arrancar

```bash
cd printer-dashboard
docker compose up -d --build
```

Abrir en el navegador: http://localhost:2026

## Parar

```bash
docker compose down
```

## Ver logs en tiempo real

```bash
docker compose logs -f
```

## Configuración (docker-compose.yml)

| Variable         | Por defecto | Descripción                         |
|------------------|-------------|-------------------------------------|
| IP_START         | 20          | Último octeto IP inicial            |
| IP_END           | 37          | Último octeto IP final              |
| SNMP_COMMUNITY   | public      | Community string SNMP               |
| POLL_INTERVAL    | 120         | Segundos entre escaneos automáticos |

## Nota sobre network_mode: host

El docker-compose.yml usa network_mode: host para que el contenedor
pueda enviar tráfico SNMP (UDP 161) directamente a la LAN.

- Linux: funciona sin cambios.
- macOS / Windows Docker Desktop: no soporta network_mode: host.
  En ese caso, comenta esa línea en el compose y ejecuta la app
  directamente en el host:

  ```bash
  cd app
  pip install -r requirements.txt
  python main.py
  ```
