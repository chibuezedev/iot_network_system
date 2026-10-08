"""
Local SQLite auth store. Passwords are hashed with bcrypt -- never stored
in plaintext, never round-tripped through anything reversible.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

import bcrypt

from app.common.paths import user_data_path

DB_PATH = user_data_path("users.db")
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "ChangeMe!2024"  # noqa: S105 -- documented seed, forced reset on first login


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('administrator','analyst')),
                created_at TEXT NOT NULL,
                must_reset_password INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                username TEXT NOT NULL,
                total_flows INTEGER NOT NULL DEFAULT 0,
                total_attacks INTEGER NOT NULL DEFAULT 0,
                highest_severity_tier INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                sim_time TEXT NOT NULL,
                device_name TEXT,
                device_ip TEXT,
                protocol TEXT,
                predicted_label TEXT,
                detection_confidence REAL,
                severity_tier INTEGER,
                severity_label TEXT,
                severity_confidence REAL,
                acknowledged INTEGER NOT NULL DEFAULT 0,
                feature_snapshot TEXT,
                FOREIGN KEY(session_id) REFERENCES session_log(id)
            )
            """
        )
        row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        if row["c"] == 0:
            pw_hash = bcrypt.hashpw(
                DEFAULT_ADMIN_PASSWORD.encode(), bcrypt.gensalt()
            ).decode()
            conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at, must_reset_password) "
                "VALUES (?, ?, 'administrator', ?, 1)",
                (
                    DEFAULT_ADMIN_USERNAME,
                    pw_hash,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )


def verify_login(username: str, password: str) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? AND active = 1", (username,)
        ).fetchone()
    if row is None:
        return None
    if bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
        return row
    return None


def get_user(username: str) -> Optional[sqlite3.Row]:
    """Fetch a user by username regardless of active status, for reset flows
    that need to distinguish "no such user" from "user disabled"."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


def set_password(
    username: str, new_password: str, clear_reset_flag: bool = True
) -> None:
    pw_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, must_reset_password = ? WHERE username = ?",
            (pw_hash, 0 if clear_reset_flag else 1, username),
        )


def create_user(username: str, password: str, role: str) -> None:
    if role not in ("administrator", "analyst"):
        raise ValueError("role must be 'administrator' or 'analyst'")
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at, must_reset_password) "
            "VALUES (?, ?, ?, ?, 1)",
            (username, pw_hash, role, datetime.now(timezone.utc).isoformat()),
        )


def get_user_by_id(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, username, role, created_at, must_reset_password, active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()


def list_users():
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, username, role, created_at, must_reset_password, active FROM users ORDER BY id"
        ).fetchall()


def set_user_active(user_id: int, active: bool) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET active = ? WHERE id = ?", (1 if active else 0, user_id)
        )


def set_user_role(user_id: int, role: str) -> None:
    if role not in ("administrator", "analyst"):
        raise ValueError("role must be 'administrator' or 'analyst'")
    with get_conn() as conn:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))


def update_user(
    user_id: int,
    username: str,
    role: str,
    active: bool,
    must_reset_password: bool,
    new_password: Optional[str] = None,
) -> None:
    if role not in ("administrator", "analyst"):
        raise ValueError("role must be 'administrator' or 'analyst'")

    params = [username, role, 1 if active else 0, 1 if must_reset_password else 0, user_id]
    query = (
        "UPDATE users SET username = ?, role = ?, active = ?, must_reset_password = ? WHERE id = ?"
    )
    if new_password:
        pw_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        query = (
            "UPDATE users SET username = ?, role = ?, active = ?, must_reset_password = ?, password_hash = ? "
            "WHERE id = ?"
        )
        params = [username, role, 1 if active else 0, 1 if must_reset_password else 0, pw_hash, user_id]

    with get_conn() as conn:
        conn.execute(query, params)


def start_session(username: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO session_log (started_at, username) VALUES (?, ?)",
            (datetime.now(timezone.utc).isoformat(), username),
        )
        return cur.lastrowid


def end_session(
    session_id: int, total_flows: int, total_attacks: int, highest_tier: int
) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE session_log SET ended_at = ?, total_flows = ?, total_attacks = ?, "
            "highest_severity_tier = ? WHERE id = ?",
            (
                datetime.now(timezone.utc).isoformat(),
                total_flows,
                total_attacks,
                highest_tier,
                session_id,
            ),
        )


def log_event(session_id: int, event: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO session_events
                (session_id, sim_time, device_name, device_ip, protocol, predicted_label,
                 detection_confidence, severity_tier, severity_label, severity_confidence,
                 feature_snapshot)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                event["sim_time"],
                event.get("device_name"),
                event.get("device_ip"),
                event.get("protocol"),
                event["predicted_label"],
                event["detection_confidence"],
                event["severity_tier"],
                event["severity_label"],
                event["severity_confidence"],
                event.get("feature_snapshot"),
            ),
        )


def acknowledge_event(event_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE session_events SET acknowledged = 1 WHERE id = ?", (event_id,)
        )


def fetch_events(
    session_id: Optional[int] = None, only_flagged: bool = True, limit: int = 5000
):
    query = "SELECT * FROM session_events"
    clauses, params = [], []
    if session_id is not None:
        clauses.append("session_id = ?")
        params.append(session_id)
    if only_flagged:
        clauses.append("severity_tier >= 1")
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        return conn.execute(query, params).fetchall()


def fetch_sessions(limit: int = 100):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM session_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
