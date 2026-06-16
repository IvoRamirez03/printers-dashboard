import subprocess
import threading
import time
import re
import os
import json
import asyncio
from datetime import datetime
from flask import Flask, render_template, jsonify

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
COMMUNITY     = os.getenv("SNMP_COMMUNITY", "public")
SNMP_VERSION  = "2c"
TIMEOUT       = 1
RETRIES       = 0
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 120))
PRINTERS_FILE = os.path.join(os.path.dirname(__file__), "printers.json")

# ---------------------------------------------------------------------------
# OIDs comunes — usados por ambas marcas
# ---------------------------------------------------------------------------
OID_PAGE_COUNT = "1.3.6.1.2.1.43.10.2.1.4.1.1"

# ---------------------------------------------------------------------------
# OIDs HP — Printer MIB estándar (RFC 3805)
# ---------------------------------------------------------------------------
OID_HP_SUPPLY_NAME = "1.3.6.1.2.1.43.11.1.1.6.1"
OID_HP_SUPPLY_MAX  = "1.3.6.1.2.1.43.11.1.1.8.1"
OID_HP_SUPPLY_CURR = "1.3.6.1.2.1.43.11.1.1.9.1"
OID_HP_STATUS      = "1.3.6.1.2.1.25.3.5.1.1.1"
OID_HP_ALERTS      = "1.3.6.1.2.1.43.18.1.1.8.1"

# Alertas HP que son informativas (no críticas)
HP_WARN_ALERTS = {
    "genuineHPSupplyFlow",
    "singleTrayLop",
    "engineInitializing",
}

# Alertas HP que elevan el nivel a crítico
HP_CRITICAL_ALERTS = {
    "cartridgeMissing",
    "fwUpdateFailure",
}

# ---------------------------------------------------------------------------
# OIDs Brother — MIB privada (enterprise 2435)
# Solo se usan como fallback si IPP falla
# ---------------------------------------------------------------------------
OID_BROTHER_BASE       = "1.3.6.1.4.1.2435.2.3.9.4.2.1.5.5"
OID_BROTHER_SUP_PGS    = f"{OID_BROTHER_BASE}.52.1.1.3"   # páginas restantes
OID_BROTHER_ALERTS     = f"{OID_BROTHER_BASE}.51.2.1.2"   # alertas en texto

# Mapa nombre corto IPP → nombre legible para Brother
BROTHER_IPP_NAME_MAP = {
    "BK": "Black Toner",
    "K":  "Black Toner",
    "C":  "Cyan Toner",
    "M":  "Magenta Toner",
    "Y":  "Yellow Toner",
    "W":  "Waste Toner",
    "LC": "Cyan Ink",
    "LM": "Magenta Ink",
}

# ---------------------------------------------------------------------------
# Carga de flota desde JSON
# ---------------------------------------------------------------------------

def load_printers():
    try:
        with open(PRINTERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[INFO] Flota cargada: {len(data['printers'])} impresoras")
        return data["printers"]
    except Exception as e:
        print(f"[ERROR] No se pudo cargar {PRINTERS_FILE}: {e}")
        return []

FLEET = load_printers()

# ---------------------------------------------------------------------------
# Estado global
# ---------------------------------------------------------------------------
state = {
    "printers":   [],
    "last_scan":  None,
    "scanning":   False,
    "scan_count": 0,
}
state_lock = threading.Lock()

# ---------------------------------------------------------------------------
# SNMP helpers — compartidos
# ---------------------------------------------------------------------------

def snmp_get(ip, oid):
    try:
        result = subprocess.run(
            ["snmpget", f"-v{SNMP_VERSION}", "-c", COMMUNITY,
             "-t", str(TIMEOUT), "-r", str(RETRIES), "-Oqv", ip, oid],
            capture_output=True, text=True, timeout=TIMEOUT + 1
        )
        return result.stdout.strip().strip('"')
    except Exception:
        return ""

def snmp_walk(ip, oid):
    try:
        result = subprocess.run(
            ["snmpwalk", f"-v{SNMP_VERSION}", "-c", COMMUNITY,
             "-t", str(TIMEOUT), "-r", str(RETRIES), "-Oqv", ip, oid],
            capture_output=True, text=True, timeout=(TIMEOUT + 1) * 8
        )
        lines = [l.strip().strip('"') for l in result.stdout.strip().splitlines() if l.strip()]
        return lines
    except Exception:
        return []

def is_error(val):
    return not val or "No Such" in val or "error" in val.lower()

def get_page_count(ip):
    raw = snmp_get(ip, OID_PAGE_COUNT)
    if raw and not is_error(raw) and raw.strip().isdigit():
        return raw.strip()
    return None

# ---------------------------------------------------------------------------
# Clasificación de nivel — compartida
# ---------------------------------------------------------------------------

def classify_pct(pct):
    if pct <= 15:    return "critical"
    elif pct <= 40:  return "low"
    else:            return "ok"

def classify_pages(pages):
    if pages < 100:   return "critical"
    elif pages < 300: return "low"
    else:             return "ok"

def printer_level_from_supplies(supplies, critical_alerts=None):
    pct_values = [s["pct"] for s in supplies if s["pct"] is not None]
    min_pct    = min(pct_values) if pct_values else None

    levels = [s["level"] for s in supplies if s["level"] != "unknown"]
    if min_pct is None and levels:
        if "critical" in levels:  return "critical", None
        elif "low" in levels:     return "low", None
        else:                     return "ok", None

    if min_pct is None:          level = "unknown"
    elif min_pct <= 15:          level = "critical"
    elif min_pct <= 40:          level = "low"
    else:                        level = "ok"

    if critical_alerts and any(a in HP_CRITICAL_ALERTS for a in critical_alerts):
        level = "critical"

    return level, min_pct

# ===========================================================================
# BLOQUE HP
# Protocolo: SNMP Printer MIB estándar (RFC 3805)
# Estado:    hrPrinterStatus (OID_HP_STATUS)
# Tóner:     OIDs 43.11.x — nombre, máximo, actual → porcentaje
# Alertas:   OID 43.18.x — strings de alerta
# Páginas:   OID_PAGE_COUNT
# ===========================================================================

def hp_get_status(ip):
    """
    hrPrinterStatus values:
      1=other, 2=unknown, 3=idle, 4=printing, 5=warmup
    """
    raw = snmp_get(ip, OID_HP_STATUS)
    if is_error(raw):
        return "unknown"
    mapping = {
        "1": "other",
        "2": "unknown",
        "3": "idle",
        "4": "printing",
        "5": "warmup",
    }
    return mapping.get(raw, raw or "unknown")

def hp_get_alerts(ip):
    """Alertas SNMP estándar. Filtra valores de relleno."""
    lines = snmp_walk(ip, OID_HP_ALERTS)
    return [
        a for a in lines
        if a and a not in ("Sleep", "Espera") and not is_error(a)
    ]

def hp_get_supplies(ip):
    """
    Lee consumibles desde Printer MIB estándar.
    Devuelve porcentaje calculado: round((current * 100) / maximum).
    """
    names_list = snmp_walk(ip, OID_HP_SUPPLY_NAME)
    max_list   = snmp_walk(ip, OID_HP_SUPPLY_MAX)
    curr_list  = snmp_walk(ip, OID_HP_SUPPLY_CURR)

    supplies = []
    for i, sname in enumerate(names_list):
        sname = " ".join(sname.split())   # colapsar espacios múltiples
        if not sname:
            continue
        max_v  = max_list[i].strip()  if i < len(max_list)  else ""
        curr_v = curr_list[i].strip() if i < len(curr_list) else ""

        try:
            max_i  = int(max_v)
            curr_i = int(curr_v)
            if max_i <= 0:
                raise ValueError
            pct = None if curr_i < 0 else round((curr_i * 100) / max_i)
        except (ValueError, ZeroDivisionError):
            pct = None

        supplies.append({
            "name":  sname,
            "pct":   pct,
            "pages": None,
            "level": classify_pct(pct) if pct is not None else "unknown",
        })

    return supplies

def scan_hp(printer_def):
    """Escaneo completo de una impresora HP."""
    ip = printer_def["ip"]

    status   = hp_get_status(ip)
    pages    = get_page_count(ip)
    alerts   = hp_get_alerts(ip)
    supplies = hp_get_supplies(ip)

    level, min_pct = printer_level_from_supplies(supplies, alerts)

    return {
        **base_result(printer_def),
        "status":        status,
        "pages":         pages,
        "alerts":        alerts,
        "supplies":      supplies,
        "level":         level,
        "min_pct":       min_pct,
        "supply_source": "snmp_standard",
        "online":        status != "unknown",
    }

# ===========================================================================
# BLOQUE BROTHER
# Protocolo principal:  IPP puerto 631
# Protocolo fallback:   SNMP MIB privada Brother (enterprise 2435)
# Estado:    IPP → printer.state.printer_state
# Tóner:     IPP → printer.markers (level 0-100, name, marker_type)
# Alertas:   SNMP MIB privada → OID_BROTHER_ALERTS (.51.2.1.2)
# Páginas:   SNMP estándar → OID_PAGE_COUNT
# ===========================================================================

async def _brother_ipp_query(ip):
    """
    Consulta IPP a Brother.
    Devuelve (status, markers) o (None, []) si falla.
    """
    import pyipp
    try:
        async with pyipp.IPP(f"ipp://{ip}:631/ipp/print") as client:
            printer = await client.printer()
            state   = getattr(printer, "state",   None)
            markers = getattr(printer, "markers", None) or []
            status  = getattr(state, "printer_state", None) if state else None
            return status, markers
    except Exception as e:
        print(f"[IPP] {ip} error: {e}")
        return None, []

def brother_ipp_query(ip):
    """Wrapper síncrono para la consulta IPP de Brother."""
    try:
        loop   = asyncio.new_event_loop()
        result = loop.run_until_complete(_brother_ipp_query(ip))
        loop.close()
        return result
    except Exception as e:
        print(f"[IPP] {ip} wrapper error: {e}")
        return None, []

def brother_parse_ipp_supplies(markers, defined_supplies):
    """
    Convierte la lista de Marker IPP en el formato de supplies del dashboard.
    Si hay supplies definidos en el JSON, los usa como referencia de nombres.
    Si no, infiere el nombre desde el mapa BROTHER_IPP_NAME_MAP.
    """
    supplies = []
    for i, m in enumerate(markers):
        raw_name = getattr(m, "name",  "") or ""
        level_v  = getattr(m, "level", -1)
        pct      = int(level_v) if isinstance(level_v, int) and level_v >= 0 else None

        # Nombre: usar definición del JSON si existe, si no inferir del mapa
        if defined_supplies and i < len(defined_supplies):
            display_name = defined_supplies[i]["name"]
        else:
            display_name = BROTHER_IPP_NAME_MAP.get(raw_name.upper(), raw_name)

        supplies.append({
            "name":  display_name,
            "pct":   pct,
            "pages": None,
            "level": classify_pct(pct) if pct is not None else "unknown",
        })
    return supplies

def brother_get_alerts(ip):
    """
    Alertas desde MIB privada Brother (.51.2.1.2).
    Filtra duplicados y hex dumps.
    """
    lines = snmp_walk(ip, OID_BROTHER_ALERTS)
    seen, alerts = set(), []
    for a in lines:
        a = a.strip()
        if not a or a in seen:
            continue
        if re.match(r'^([0-9A-Fa-f]{2}\s+){4,}', a):
            continue
        seen.add(a)
        alerts.append(a)
    return alerts

def brother_get_supplies_snmp_fallback(ip, defined_supplies):
    """
    Fallback SNMP MIB privada Brother cuando IPP no devuelve markers.
    Usa páginas restantes estimadas en lugar de porcentaje.
    Lee los índices en el orden definido en printers.json.
    """
    pgs_lines = snmp_walk(ip, OID_BROTHER_SUP_PGS)
    supplies  = []

    for i, sup_def in enumerate(defined_supplies):
        pages = None
        if i < len(pgs_lines):
            try:
                pages = int(pgs_lines[i].strip())
            except ValueError:
                pass

        level = classify_pages(pages) if pages is not None else "unknown"

        supplies.append({
            "name":  sup_def["name"],
            "pct":   None,
            "pages": pages,
            "level": level,
        })

    return supplies

def scan_brother(printer_def):
    """
    Escaneo completo de una impresora Brother.
    1. IPP  → estado + niveles de tóner (porcentaje real)
    2. SNMP → alertas (MIB privada) + páginas (MIB estándar)
    3. Si IPP no devuelve markers → fallback SNMP MIB privada para niveles
    """
    ip               = printer_def["ip"]
    defined_supplies = printer_def.get("supplies", [])

    # --- IPP: estado y niveles de tóner ---
    ipp_status, markers = brother_ipp_query(ip)

    if markers:
        supplies      = brother_parse_ipp_supplies(markers, defined_supplies)
        supply_source = "ipp"
    else:
        print(f"[Brother] {ip}: IPP sin markers, usando SNMP MIB privada")
        supplies      = brother_get_supplies_snmp_fallback(ip, defined_supplies)
        supply_source = "snmp_brother"

    # --- SNMP: alertas y páginas (siempre desde SNMP) ---
    alerts = brother_get_alerts(ip)
    pages  = get_page_count(ip)

    # --- Estado: IPP si disponible, si no SNMP no aplica en Brother ---
    status = ipp_status or "unknown"

    level, min_pct = printer_level_from_supplies(supplies)

    return {
        **base_result(printer_def),
        "status":        status,
        "pages":         pages,
        "alerts":        alerts,
        "supplies":      supplies,
        "level":         level,
        "min_pct":       min_pct,
        "supply_source": supply_source,
        "online":        ipp_status is not None,
    }

# ===========================================================================
# Datos estáticos — compartidos
# ===========================================================================

def base_result(p):
    """Datos del JSON que no cambian entre escaneos."""
    return {
        "ip":         p["ip"],
        "name":       p["name"],
        "model":      p.get("model", ""),
        "serial":     p.get("serial", ""),
        "toner_ref":  p.get("toner_ref", ""),
        "connection": p.get("connection", ""),
        "type":       p.get("type", ""),
    }

# ---------------------------------------------------------------------------
# Escaneo por impresora — enrutador
# ---------------------------------------------------------------------------

def scan_printer(printer_def):
    protocol = printer_def.get("protocol", "snmp_standard")

    if protocol == "none":
        return {
            **base_result(printer_def),
            "status": "unknown", "pages": None, "alerts": [],
            "supplies": [], "level": "unknown", "min_pct": None,
            "supply_source": "none", "online": False,
        }
    elif protocol == "snmp_brother":
        return scan_brother(printer_def)
    else:
        return scan_hp(printer_def)

# ---------------------------------------------------------------------------
# Bucle de escaneo
# ---------------------------------------------------------------------------

def run_scan():
    printers = []
    for printer_def in FLEET:
        try:
            result = scan_printer(printer_def)
            printers.append(result)
        except Exception as e:
            print(f"[ERROR] {printer_def['ip']}: {e}")
            printers.append({
                **base_result(printer_def),
                "status": "unknown", "pages": None, "alerts": [],
                "supplies": [], "level": "unknown", "min_pct": None,
                "supply_source": "error", "online": False,
            })

    with state_lock:
        state["printers"]    = printers
        state["last_scan"]   = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        state["scanning"]    = False
        state["scan_count"] += 1

def scan_loop():
    with state_lock:
        state["scanning"] = True
    try:
        run_scan()
    except Exception as e:
        with state_lock:
            state["scanning"] = False
        print(f"[ERROR] Scan inicial fallido: {e}")

    while True:
        time.sleep(POLL_INTERVAL)
        with state_lock:
            state["scanning"] = True
        try:
            run_scan()
        except Exception as e:
            with state_lock:
                state["scanning"] = False
            print(f"[ERROR] Scan fallido: {e}")

# ---------------------------------------------------------------------------
# Rutas Flask
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", poll_interval=POLL_INTERVAL)

@app.route("/api/status")
def api_status():
    with state_lock:
        return jsonify({
            "printers":   state["printers"],
            "last_scan":  state["last_scan"],
            "scanning":   state["scanning"],
            "scan_count": state["scan_count"],
        })

@app.route("/api/scan", methods=["POST"])
def api_trigger_scan():
    with state_lock:
        if state["scanning"]:
            return jsonify({"ok": False, "msg": "Escaneo ya en curso"}), 409
        state["scanning"] = True
    t = threading.Thread(target=run_scan, daemon=True)
    t.start()
    return jsonify({"ok": True})

@app.route('/inventario')
def inventario():
    return render_template('inventario.html')

# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    scanner_thread = threading.Thread(target=scan_loop, daemon=True)
    scanner_thread.start()
    app.run(host="0.0.0.0", port=2026, debug=False)