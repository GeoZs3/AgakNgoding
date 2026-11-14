import sqlite3
from functools import wraps
from typing import Any, Dict, Optional
from flask import flash, g, redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


def authenticate_user(
    db: sqlite3.Connection, username: str, password: str
) -> Optional[Dict[str, Any]]:
    """Memverifikasi kredensial Guru atau Penanggung Jawab (P)."""
    query = """
        SELECT
            u.id,
            u.username,
            u.password_hash,
            u.full_name,
            u.role,
            u.manager_code,
            u.is_active,
            m.is_plant_manager
        FROM users u
        LEFT JOIN managers m ON u.manager_code = m.code
        WHERE u.username = ? AND u.is_active = 1
    """
    row = db.execute(query, (username.strip(),)).fetchone()
    if not row:
        return None

    if not check_password_hash(row["password_hash"], password):
        return None

    # Pastikan hanya role 'guru' atau 'p_manager' yang berstatus pengurus tanaman (5P) yang diizinkan
    if row["role"] == "p_manager" and row["is_plant_manager"] != 1:
        return None

    return dict(row)


def create_user_account(
    db: sqlite3.Connection,
    username: str,
    password: str,
    full_name: str,
    role: str,
    manager_code: Optional[str] = None,
) -> int:
    """Helper untuk mendaftarkan akun Guru atau P pengurus tanaman ke database."""
    pw_hash = generate_password_hash(password)
    with db:
        cursor = db.execute(
            """
            INSERT INTO users (username, password_hash, full_name, role, manager_code)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username.strip(), pw_hash, full_name.strip(), role, manager_code),
        )
    return cursor.lastrowid


def load_logged_in_user(db: sqlite3.Connection) -> None:
    """Memuat data pengguna aktif ke objek flask.g pada setiap request."""
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        row = db.execute(
            """
            SELECT id, username, full_name, role, manager_code
            FROM users
            WHERE id = ? AND is_active = 1
            """,
            (user_id,),
        ).fetchone()
        g.user = dict(row) if row else None


def editor_required(view):
    """Decorator pembatas akses: hanya Guru dan 5 P pengurus tanaman yang dapat mengakses."""
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.get("user") is None:
            flash("Akses ditolak. Silakan login sebagai Guru atau P pengurus tanaman.", "error")
            return redirect(url_for("auth.login"))
        return view(**kwargs)

    return wrapped_view