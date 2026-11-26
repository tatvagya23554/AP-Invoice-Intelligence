import sqlite3, json
from pathlib import Path
DB_PATH = Path(__file__).parent / "data" / "runs.db"

def connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        processed_at TEXT, filename TEXT, status TEXT, vendor_name TEXT,
        invoice_number TEXT, po_number TEXT, total TEXT, file_hash TEXT UNIQUE,
        result_json TEXT NOT NULL
    )""")
    con.commit()
    return con

def save_run(result):
    con = connect()
    con.execute("""INSERT OR IGNORE INTO runs
    (processed_at,filename,status,vendor_name,invoice_number,po_number,total,file_hash,result_json)
    VALUES (?,?,?,?,?,?,?,?,?)""", (
        result["processed_at"], result["filename"], result["status"], result.get("vendor_name"),
        result.get("invoice_number"), result.get("po_number"), result.get("total"),
        result["file_hash"], json.dumps(result)
    ))
    con.commit()
    con.close()

def history():
    con = connect()
    rows = con.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
    con.close()
    return [dict(r) for r in rows]

def clear_history():
    con = connect()
    con.execute("DELETE FROM runs")
    con.commit()
    con.close()
