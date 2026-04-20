import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent / "data" / "pyjhora.db"

AUTOSAVE_KEY = "__last__"

PROFILE_COLUMNS = ("name", "gender", "date", "time", "city",
                   "latitude", "longitude", "timezone")


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                label      TEXT NOT NULL UNIQUE,
                name       TEXT DEFAULT '',
                gender     TEXT DEFAULT '',
                date       TEXT DEFAULT '',
                time       TEXT DEFAULT '',
                city       TEXT DEFAULT '',
                latitude   REAL DEFAULT 0,
                longitude  REAL DEFAULT 0,
                timezone   REAL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
        """)


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "label": row["label"],
        "name": row["name"],
        "gender": row["gender"],
        "date": row["date"],
        "time": row["time"],
        "city": row["city"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "timezone": row["timezone"],
        "updated_at": row["updated_at"],
    }


def upsert_profile(label: str, fields: dict) -> dict:
    now = datetime.utcnow().isoformat(timespec="seconds")
    data = {k: fields.get(k, "") for k in PROFILE_COLUMNS}
    for num_key in ("latitude", "longitude", "timezone"):
        try:
            data[num_key] = float(data[num_key]) if data[num_key] != "" else 0.0
        except (TypeError, ValueError):
            data[num_key] = 0.0
    with _conn() as conn:
        conn.execute("""
            INSERT INTO profiles (label, name, gender, date, time, city,
                                  latitude, longitude, timezone, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(label) DO UPDATE SET
                name=excluded.name,
                gender=excluded.gender,
                date=excluded.date,
                time=excluded.time,
                city=excluded.city,
                latitude=excluded.latitude,
                longitude=excluded.longitude,
                timezone=excluded.timezone,
                updated_at=excluded.updated_at
        """, (label, data["name"], data["gender"], data["date"], data["time"],
              data["city"], data["latitude"], data["longitude"], data["timezone"], now))
        row = conn.execute("SELECT * FROM profiles WHERE label = ?", (label,)).fetchone()
    return _row_to_dict(row)


def get_profile(label: str) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE label = ?", (label,)).fetchone()
    return _row_to_dict(row) if row else None


def get_profile_by_id(profile_id: int) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_profiles(include_autosave: bool = False) -> list[dict]:
    with _conn() as conn:
        if include_autosave:
            rows = conn.execute("SELECT * FROM profiles ORDER BY updated_at DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM profiles WHERE label != ? ORDER BY updated_at DESC",
                (AUTOSAVE_KEY,)
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def delete_profile(profile_id: int) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "DELETE FROM profiles WHERE id = ? AND label != ?",
            (profile_id, AUTOSAVE_KEY)
        )
        return cur.rowcount > 0
