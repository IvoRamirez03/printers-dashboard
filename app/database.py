# app/database.py
import os
import json
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "printers.sqlite3")
JSON_PATH = os.path.join(os.path.dirname(__file__), "printers.json")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Permite acceso estilo diccionario
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    """Crea las tablas e importa el JSON inicial si la base de datos está vacía."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS printers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        model TEXT,
        serial TEXT,
        toner_ref TEXT,
        connection TEXT,
        protocol TEXT,
        type TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS supplies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        printer_id INTEGER NOT NULL,
        supply_key_id INTEGER,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        FOREIGN KEY (printer_id) REFERENCES printers(id) ON DELETE CASCADE
    )
    ''')

    conn.commit()

    # Si la tabla printers está vacía y existe printers.json, migrar datos
    cursor.execute("SELECT COUNT(*) FROM printers")
    if cursor.fetchone()[0] == 0 and os.path.exists(JSON_PATH):
        print("[INFO] Migrando printers.json a SQLite...")
        try:
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            for p in data.get("printers", []):
                cursor.execute('''
                INSERT INTO printers (ip, name, model, serial, toner_ref, connection, protocol, type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    p.get("ip"), p.get("name"), p.get("model"), p.get("serial"),
                    p.get("toner_ref"), p.get("connection"), p.get("protocol"), p.get("type")
                ))
                printer_id = cursor.lastrowid

                for s in p.get("supplies", []):
                    cursor.execute('''
                    INSERT INTO supplies (printer_id, supply_key_id, name, type)
                    VALUES (?, ?, ?, ?)
                    ''', (printer_id, s.get("id"), s.get("name"), s.get("type")))

            conn.commit()
            print("[INFO] Migración a SQLite completada exitosamente.")
        except Exception as e:
            print(f"[ERROR] Error al migrar JSON a SQLite: {e}")

    conn.close()

def load_printers_from_db():
    """Lee las impresoras desde SQLite reconstruyendo la estructura para main.py."""
    init_db()  # Asegura que la BD exista antes de leer
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM printers")
    printers_rows = cursor.fetchall()

    fleet = []
    for p in printers_rows:
        printer_dict = dict(p)
        printer_id = printer_dict["id"]

        # Obtener los suministros mapeados para esta impresora
        cursor.execute(
            "SELECT supply_key_id AS id, name, type FROM supplies WHERE printer_id = ?", 
            (printer_id,)
        )
        supplies_rows = cursor.fetchall()

        # Si es HP o no tiene supplies, supplies_rows será [], manteniendo la lógica intacta
        printer_dict["supplies"] = [dict(s) for s in supplies_rows]
        fleet.append(printer_dict)

    conn.close()
    return fleet