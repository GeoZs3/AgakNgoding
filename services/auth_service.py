import sqlite3
import secrets
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
            u.is_admin,
            u.is_superadmin,
            u.can_edit_plants,
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

    if (
        row["role"] == "p_manager"
        and row["is_plant_manager"] != 1
        and not row["is_admin"]
        and not row["is_superadmin"]
    ):
        return None

    return dict(row)


def create_user_account(
    db: sqlite3.Connection,
    username: str,
    password: str,
    full_name: str,
    role: str,
    manager_code: Optional[str] = None,
    can_edit_plants: bool = True,
    is_admin: bool = False,
    is_superadmin: bool = False,
) -> int:
    """Helper untuk mendaftarkan akun Guru atau P pengurus tanaman ke database."""
    is_admin = is_admin or is_superadmin
    pw_hash = generate_password_hash(password)
    with db:
        cursor = db.execute(
            """
            INSERT INTO users (
                username, password_hash, full_name, role, manager_code,
                can_edit_plants, is_admin, is_superadmin
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username.strip(),
                pw_hash,
                full_name.strip(),
                role,
                manager_code,
                int(can_edit_plants),
                int(is_admin),
                int(is_superadmin),
            ),
        )
    return cursor.lastrowid


def load_logged_in_user(db: sqlite3.Connection) -> None:
    """Memuat data pengguna aktif ke objek flask.g pada setiap request."""
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
        return

    row = db.execute(
        """
        SELECT id, username, full_name, role, manager_code,
               is_admin, is_superadmin, can_edit_plants
        FROM users
        WHERE id = ? AND is_active = 1
        """,
        (user_id,),
    ).fetchone()
    if row is None:
        presence_id = session.pop("presence_id", None)
        if presence_id:
            with db:
                db.execute(
                    "DELETE FROM active_sessions WHERE session_id = ?",
                    (presence_id,),
                )
        g.user = None
        return

    g.user = dict(row)
    presence_id = session.get("presence_id")
    if not presence_id:
        presence_id = secrets.token_urlsafe(32)
        session["presence_id"] = presence_id

    with db:
        db.execute(
            """
            INSERT INTO active_sessions (session_id, user_id, last_seen_at)
            VALUES (?, ?, datetime('now', 'localtime'))
            ON CONFLICT(session_id) DO UPDATE SET
                user_id = excluded.user_id,
                last_seen_at = excluded.last_seen_at
            """,
            (presence_id, user_id),
        )
        db.execute(
            """
            UPDATE users
            SET last_seen_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (user_id,),
        )

def editor_required(view):
    """Batasi perubahan data tanaman pada akun P, Guru, dan Admin."""
    @wraps(view)
    def wrapped_view(**kwargs):
        user = g.get("user")
        if user is None:
            flash("Akses ditolak. Silakan login terlebih dahulu.", "error")
            return redirect(url_for("auth.login"))
        if (
            user["role"] not in ("p_manager", "guru")
            and not user["is_admin"]
            and not user["is_superadmin"]
        ):
            flash("Akun ini tidak memiliki hak untuk mengubah data tanaman.", "error")
            return redirect(url_for("main.index", masuk=1))
        return view(**kwargs)

    return wrapped_view


def admin_required(view):
    """Batasi panel monitoring dan pengelolaan akun pada administrator."""
    @wraps(view)
    def wrapped_view(**kwargs):
        user = g.get("user")
        if user is None:
            flash("Silakan login untuk membuka panel admin.", "error")
            return redirect(url_for("auth.login"))
        if not user["is_admin"] and not user["is_superadmin"]:
            flash("Akses panel admin hanya untuk administrator.", "error")
            return redirect(url_for("main.index", masuk=1))
        return view(**kwargs)

    return wrapped_view