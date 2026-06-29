import sqlite3
import os
import json
import secrets
from datetime import datetime, date
from typing import List, Dict, Optional

# In Docker viene impostato via env (es. /app/data/primoit.db); in locale ricade su backend/data/
DB_PATH = os.getenv("DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "primoit.db")


def get_db():
    """Get database connection with row factory."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database schema."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT NOT NULL,
            aff_sub1 TEXT,
            aff_sub2 TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            http_status INTEGER,
            worldfilia_response TEXT,
            error TEXT
        )
    """)
    # PrimoIT Shop — deals (mini-CRM richieste preventivo)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            ref TEXT,
            customer_name TEXT,
            customer_contact TEXT,
            items_json TEXT NOT NULL,
            total REAL,
            status TEXT NOT NULL DEFAULT 'Nuovo',
            notes TEXT,
            details_json TEXT,
            updated_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS icecat_overrides (
            product_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            value TEXT NOT NULL,
            brand TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    # Impostazioni configurabili da admin (es. pixel/tracking)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    # migrazione DB esistenti: aggiungi details_json se manca
    try:
        cursor.execute("ALTER TABLE deals ADD COLUMN details_json TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def save_lead(
    name: str,
    phone: str,
    address: str,
    aff_sub1: str = None,
    aff_sub2: str = None,
    status: str = "pending",
    http_status: int = None,
    worldfilia_response: str = None,
    error: str = None,
) -> int:
    """Save a lead to the database. Returns the lead ID."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO leads (name, phone, address, aff_sub1, aff_sub2, status, http_status, worldfilia_response, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (name, phone, address, aff_sub1, aff_sub2, status, http_status, worldfilia_response, error),
    )
    conn.commit()
    lead_id = cursor.lastrowid
    conn.close()
    return lead_id


def get_leads(page: int = 1, limit: int = 50, date_filter: str = None) -> Dict:
    """Get paginated leads list."""
    conn = get_db()
    cursor = conn.cursor()

    offset = (page - 1) * limit

    if date_filter:
        cursor.execute(
            "SELECT COUNT(*) FROM leads WHERE DATE(created_at) = ?", (date_filter,)
        )
        total = cursor.fetchone()[0]
        cursor.execute(
            "SELECT * FROM leads WHERE DATE(created_at) = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (date_filter, limit, offset),
        )
    else:
        cursor.execute("SELECT COUNT(*) FROM leads")
        total = cursor.fetchone()[0]
        cursor.execute(
            "SELECT * FROM leads ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )

    rows = cursor.fetchall()
    leads = [dict(row) for row in rows]
    conn.close()

    return {
        "leads": leads,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if total > 0 else 1,
    }


def get_lead_stats() -> Dict:
    """Get lead statistics."""
    conn = get_db()
    cursor = conn.cursor()

    today = date.today().isoformat()

    cursor.execute("SELECT COUNT(*) FROM leads")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM leads WHERE DATE(created_at) = ?", (today,))
    today_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM leads WHERE status = 'success'")
    success = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM leads WHERE status = 'failed'")
    failed = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM leads WHERE status = 'success' AND DATE(created_at) = ?", (today,))
    today_success = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM leads WHERE status = 'failed' AND DATE(created_at) = ?", (today,))
    today_failed = cursor.fetchone()[0]

    conn.close()

    return {
        "total": total,
        "today": today_count,
        "success": success,
        "failed": failed,
        "today_success": today_success,
        "today_failed": today_failed,
        "success_rate": round((success / total * 100), 1) if total > 0 else 0,
        "date": today,
    }


# ============ PrimoIT Shop — Deals (mini-CRM) ============

DEAL_STATUSES = [
    "Nuovo", "Contattato", "Preventivo inviato",
    "Pagato acconto 20%", "Pagato", "Spedito", "Perso",
]


def create_deal(items, customer_name=None, customer_contact=None, total=None) -> Dict:
    """Crea un deal dal carrello dello shop. Ritorna {id, ref}."""
    conn = get_db()
    cursor = conn.cursor()
    ref = "PR-" + secrets.token_hex(3).upper()
    cursor.execute(
        """INSERT INTO deals (ref, customer_name, customer_contact, items_json, total, status)
           VALUES (?, ?, ?, ?, ?, 'Nuovo')""",
        (ref, customer_name, customer_contact, json.dumps(items, ensure_ascii=False), total),
    )
    conn.commit()
    deal_id = cursor.lastrowid
    conn.close()
    return {"id": deal_id, "ref": ref}


def get_deals(status: str = None) -> List[Dict]:
    """Lista deal (opz. filtrata per stato), più recenti prima."""
    conn = get_db()
    cursor = conn.cursor()
    if status:
        cursor.execute("SELECT * FROM deals WHERE status = ? ORDER BY created_at DESC", (status,))
    else:
        cursor.execute("SELECT * FROM deals ORDER BY created_at DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    for r in rows:
        try:
            r["items"] = json.loads(r.get("items_json") or "[]")
        except Exception:
            r["items"] = []
        try:
            r["details"] = json.loads(r.get("details_json") or "{}")
        except Exception:
            r["details"] = {}
    return rows


def get_deal(deal_id: int) -> Optional[Dict]:
    """Un singolo deal (con items e details già parse), o None."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM deals WHERE id = ?", (deal_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    r = dict(row)
    try:
        r["items"] = json.loads(r.get("items_json") or "[]")
    except Exception:
        r["items"] = []
    try:
        r["details"] = json.loads(r.get("details_json") or "{}")
    except Exception:
        r["details"] = {}
    return r


def update_deal(deal_id: int, status: str = None, notes: str = None, details: dict = None) -> bool:
    """Aggiorna stato, note e/o dettagli (contatto/spedizione/fatturazione/tracking) di un deal."""
    conn = get_db()
    cursor = conn.cursor()
    sets, vals = [], []
    if status is not None:
        sets.append("status = ?")
        vals.append(status)
    if notes is not None:
        sets.append("notes = ?")
        vals.append(notes)
    if details is not None:
        sets.append("details_json = ?")
        vals.append(json.dumps(details, ensure_ascii=False))
    if not sets:
        conn.close()
        return False
    sets.append("updated_at = datetime('now')")
    vals.append(deal_id)
    cursor.execute("UPDATE deals SET " + ", ".join(sets) + " WHERE id = ?", vals)
    conn.commit()
    ok = cursor.rowcount > 0
    conn.close()
    return ok


# ============ PrimoIT Shop — Icecat manual overrides ============

def get_icecat_overrides() -> Dict[str, Dict]:
    """Ritorna gli override Icecat manuali: product_id -> {kind, value, brand, updated_at}."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT product_id, kind, value, brand, updated_at FROM icecat_overrides ORDER BY product_id")
    rows = cursor.fetchall()
    conn.close()
    return {row["product_id"]: {
        "kind": row["kind"],
        "value": row["value"],
        "brand": row["brand"],
        "updated_at": row["updated_at"],
    } for row in rows}


def upsert_icecat_override(product_id: str, kind: str, value: str, brand: str = None) -> Dict:
    """Crea/aggiorna un override Icecat manuale per uno SKU catalogo."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO icecat_overrides (product_id, kind, value, brand, updated_at)
           VALUES (?, ?, ?, ?, datetime('now'))
           ON CONFLICT(product_id) DO UPDATE SET
             kind=excluded.kind,
             value=excluded.value,
             brand=excluded.brand,
             updated_at=datetime('now')""",
        (product_id, kind, value, brand),
    )
    conn.commit()
    cursor.execute("SELECT product_id, kind, value, brand, updated_at FROM icecat_overrides WHERE product_id = ?", (product_id,))
    row = dict(cursor.fetchone())
    conn.close()
    return row


def delete_icecat_override(product_id: str) -> bool:
    """Rimuove un override Icecat manuale. Ritorna True se esisteva."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM icecat_overrides WHERE product_id = ?", (product_id,))
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


# ============ Impostazioni (key-value) configurabili da admin ============

def get_settings() -> Dict[str, str]:
    """Tutte le impostazioni come dict key->value."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    return {row["key"]: (row["value"] or "") for row in rows}


def set_settings(values: Dict[str, str]) -> None:
    """Upsert di più impostazioni in una volta."""
    conn = get_db()
    cursor = conn.cursor()
    for key, value in values.items():
        cursor.execute(
            """INSERT INTO settings (key, value, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')""",
            (key, value if value is not None else ""),
        )
    conn.commit()
    conn.close()
