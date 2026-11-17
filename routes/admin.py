import re
import secrets
import sqlite3
from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for
from database.connection import get_db
from services.auth_service import admin_required, authenticate_user, create_user_account
from werkzeug.security import generate_password_hash

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
ONLINE_WINDOW_SQL = "datetime('now', 'localtime', '-2 minutes')"
USERNAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]{2,50}\Z")


def _validate_csrf_token() -> None:
    expected = session.get("admin_csrf_token", "")
    submitted = request.form.get("_csrf_token", "")
    if not expected or not secrets.compare_digest(expected, submitted):
        abort(400)


def _validate_role_and_manager(
    account_type: str,
    manager_code: str,
    db: sqlite3.Connection,
    existing=None,
):
    if account_type == "admin":
        if existing and existing["role"] == "p_manager":
            return existing["role"], existing["manager_code"], None
        return "guru", None, None
    if account_type not in ("guru", "p_manager"):
        return None, None, "Role akun tidak valid."
    if account_type == "guru":
        return "guru", None, None
    if not manager_code:
        return None, None, "Pilih kode P untuk akun pengelola."
    manager = db.execute(
        "SELECT code FROM managers WHERE code = ? AND is_plant_manager = 1",
        (manager_code,),
    ).fetchone()
    if manager is None:
        return None, None, "Kode tersebut bukan penanggung jawab tanaman yang aktif."
    return "p_manager", manager_code, None


def _dashboard_data(db: sqlite3.Connection):
    summary = db.execute(
        """
        SELECT
            COUNT(*) AS plant_records,
            COALESCE(SUM(quantity), 0) AS plant_units,
            COALESCE(SUM(CASE WHEN status = 'Hidup' THEN quantity ELSE 0 END), 0) AS living_units,
            COALESCE(SUM(CASE WHEN status = 'Perawatan Khusus' THEN quantity ELSE 0 END), 0) AS care_units,
            COALESCE(SUM(CASE WHEN status = 'Layu' THEN quantity ELSE 0 END), 0) AS wilted_units,
            COALESCE(SUM(CASE WHEN status = 'Mati' THEN quantity ELSE 0 END), 0) AS dead_units
        FROM plants
        """
    ).fetchone()
    total_units = int(summary["plant_units"])

    plant_types = [
        dict(row)
        for row in db.execute(
            """
            SELECT pt.name, COUNT(p.uid) AS plant_records,
                   COALESCE(SUM(p.quantity), 0) AS plant_units
            FROM plant_types pt
            LEFT JOIN plants p ON p.plant_type_id = pt.id
            GROUP BY pt.id, pt.name
            ORDER BY plant_units DESC, pt.name COLLATE NOCASE
            """
        )
    ]
    for item in plant_types:
        item["percentage"] = (
            round(item["plant_units"] * 100 / total_units, 1)
            if total_units
            else 0
        )

    status_rows = [
        dict(row)
        for row in db.execute(
            """
            SELECT status, COUNT(*) AS plant_records,
                   COALESCE(SUM(quantity), 0) AS plant_units
            FROM plants
            GROUP BY status
            ORDER BY plant_units DESC, status COLLATE NOCASE
            """
        )
    ]
    for item in status_rows:
        item["percentage"] = (
            round(item["plant_units"] * 100 / total_units, 1)
            if total_units
            else 0
        )

    accounts = [
        dict(row)
        for row in db.execute(
            f"""
            SELECT u.id, u.username, u.full_name, u.role, u.manager_code,
                   u.is_active, u.is_admin, u.is_superadmin, u.can_edit_plants, u.created_at,
                   u.last_seen_at,
                   COUNT(DISTINCT CASE
                       WHEN s.last_seen_at >= {ONLINE_WINDOW_SQL}
                       THEN s.session_id
                   END) AS active_sessions
            FROM users u
            LEFT JOIN active_sessions s ON s.user_id = u.id
            GROUP BY u.id
            ORDER BY u.is_superadmin DESC, u.is_admin DESC, u.role,
                     u.manager_code, u.username COLLATE NOCASE
            """
        )
    ]
    for account in accounts:
        account["is_online"] = bool(account["is_active"] and account["active_sessions"])

    manager_status = [
        dict(row)
        for row in db.execute(
            f"""
            SELECT m.code, m.name AS manager_name, u.id AS user_id,
                   u.username, u.full_name, u.is_active, u.last_seen_at,
                   COUNT(DISTINCT CASE
                       WHEN s.last_seen_at >= {ONLINE_WINDOW_SQL}
                       THEN s.session_id
                   END) AS active_sessions
            FROM managers m
            LEFT JOIN users u
                ON u.manager_code = m.code AND u.role = 'p_manager'
            LEFT JOIN active_sessions s ON s.user_id = u.id
            WHERE m.is_plant_manager = 1
            GROUP BY m.code, m.name, u.id
            ORDER BY m.code
            """
        )
    ]
    for manager in manager_status:
        manager["is_online"] = bool(
            manager["is_active"] and manager["active_sessions"]
        )

    total_accounts = len(accounts)
    active_accounts = sum(bool(account["is_active"]) for account in accounts)
    online_managers = sum(
        manager["is_online"] for manager in manager_status
    )
    return {
        "summary": dict(summary),
        "plant_types": plant_types,
        "status_rows": status_rows,
        "accounts": accounts,
        "manager_status": manager_status,
        "managers": [
            dict(row)
            for row in db.execute(
                """
                SELECT code, name
                FROM managers
                WHERE is_plant_manager = 1
                ORDER BY code
                """
            )
        ],
        "metrics": {
            "total_accounts": total_accounts,
            "active_accounts": active_accounts,
            "online_managers": online_managers,
        },
        "top_type": plant_types[0] if plant_types else None,
    }


@admin_bp.route("/")
@admin_required
def dashboard():
    db = get_db()
    with db:
        db.execute(
            f"DELETE FROM active_sessions WHERE last_seen_at < "
            f"datetime('now', 'localtime', '-1 day')"
        )

    if not session.get("admin_csrf_token"):
        session["admin_csrf_token"] = secrets.token_urlsafe(32)

    return render_template(
        "admin.html",
        csrf_token=session["admin_csrf_token"],
        **_dashboard_data(db),
    )


@admin_bp.route("/login", methods=["GET", "POST"])
def admin_login():
    user = g.get("user")
    if user is not None:
        if user["is_admin"] or user["is_superadmin"]:
            return redirect(url_for("admin.dashboard"))
        flash("Akun ini tidak memiliki akses ke menu monitor.", "error")
        return redirect(url_for("main.index", masuk=1))

    if request.method == "POST":
        user = authenticate_user(
            get_db(),
            request.form.get("username", ""),
            request.form.get("password", ""),
        )
        if user is None or not (user["is_admin"] or user["is_superadmin"]):
            flash("Akun administrator tidak ditemukan atau kata sandi salah.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Selamat datang, {user['full_name']}.", "success")
            return redirect(url_for("admin.dashboard"))

    return render_template("admin_login.html")


@admin_bp.route("/accounts", methods=["POST"])
@admin_required
def create_account():
    _validate_csrf_token()
    db = get_db()

    username = request.form.get("username", "").strip()
    full_name = request.form.get("full_name", "").strip()
    password = request.form.get("password", "")
    account_type = request.form.get("role", "")
    manager_code = request.form.get("manager_code", "").strip().upper()
    is_admin = account_type == "admin"

    if not USERNAME_PATTERN.fullmatch(username):
        flash("Username harus 2–50 karakter: huruf, angka, titik, garis bawah, atau strip.", "error")
        return redirect(url_for("admin.dashboard", _anchor="accounts"))
    if not full_name or len(full_name) > 120:
        flash("Nama lengkap wajib diisi dan maksimal 120 karakter.", "error")
        return redirect(url_for("admin.dashboard", _anchor="accounts"))
    if len(password) < 8:
        flash("Kata sandi akun baru minimal 8 karakter.", "error")
        return redirect(url_for("admin.dashboard", _anchor="accounts"))

    role, manager_code, error = _validate_role_and_manager(
        account_type, manager_code, db
    )
    if error:
        flash(error, "error")
        return redirect(url_for("admin.dashboard", _anchor="accounts"))

    duplicate = db.execute(
        "SELECT 1 FROM users WHERE username = ? COLLATE NOCASE",
        (username,),
    ).fetchone()
    if duplicate:
        flash("Username tersebut sudah digunakan.", "error")
        return redirect(url_for("admin.dashboard", _anchor="accounts"))

    try:
        create_user_account(
            db=db,
            username=username,
            password=password,
            full_name=full_name,
            role=role,
            manager_code=manager_code,
            can_edit_plants=True,
            is_admin=is_admin,
        )
    except sqlite3.IntegrityError:
        flash("Akun tidak dapat dibuat karena username atau relasi datanya sudah digunakan.", "error")
        return redirect(url_for("admin.dashboard", _anchor="accounts"))

    flash(f"Akun {username} berhasil dibuat.", "success")
    return redirect(url_for("admin.dashboard", _anchor="accounts"))


@admin_bp.route("/accounts/<int:user_id>", methods=["POST"])
@admin_required
def update_account(user_id: int):
    _validate_csrf_token()
    db = get_db()
    target = db.execute(
        "SELECT id, role, manager_code, is_admin, is_superadmin FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if target is None:
        abort(404)

    username = request.form.get("username", "").strip()
    full_name = request.form.get("full_name", "").strip()
    if not USERNAME_PATTERN.fullmatch(username):
        flash("Username harus 2–50 karakter: huruf, angka, titik, garis bawah, atau strip.", "error")
        return redirect(url_for("admin.dashboard", _anchor="accounts"))
    if not full_name or len(full_name) > 120:
        flash("Nama lengkap wajib diisi dan maksimal 120 karakter.", "error")
        return redirect(url_for("admin.dashboard", _anchor="accounts"))
    duplicate = db.execute(
        "SELECT 1 FROM users WHERE username = ? COLLATE NOCASE AND id != ?",
        (username, user_id),
    ).fetchone()
    if duplicate:
        flash("Username tersebut sudah digunakan.", "error")
        return redirect(url_for("admin.dashboard", _anchor="accounts"))

    account_type = request.form.get("role", "")
    manager_code = request.form.get("manager_code", "").strip().upper()
    is_active = request.form.get("is_active") == "1"
    is_admin = account_type == "admin"
    is_superadmin = bool(is_admin and target["is_superadmin"])

    role, manager_code, error = _validate_role_and_manager(
        account_type, manager_code, db, existing=target
    )
    if error:
        flash(error, "error")
        return redirect(url_for("admin.dashboard", _anchor="accounts"))

    other_active_admins = db.execute(
        """
        SELECT COUNT(*) AS total
        FROM users
        WHERE id != ? AND (is_admin = 1 OR is_superadmin = 1) AND is_active = 1
        """,
        (user_id,),
    ).fetchone()["total"]
    if not (is_admin and is_active) and other_active_admins == 0:
        flash("Tidak dapat menonaktifkan atau mencabut admin terakhir.", "error")
        return redirect(url_for("admin.dashboard", _anchor="accounts"))

    with db:
        db.execute(
            """
            UPDATE users
            SET username = ?, full_name = ?, role = ?, manager_code = ?, can_edit_plants = ?,
                is_admin = ?, is_superadmin = ?, is_active = ?
            WHERE id = ?
            """,
            (
                username,
                full_name,
                role,
                manager_code,
                1,
                int(is_admin),
                int(is_superadmin),
                int(is_active),
                user_id,
            ),
        )

    flash("Role, status, dan hak akses akun berhasil diperbarui.", "success")
    return redirect(url_for("admin.dashboard", _anchor="accounts"))


@admin_bp.route("/accounts/<int:user_id>/password", methods=["GET", "POST"])
@admin_required
def reset_account_password(user_id: int):
    db = get_db()
    account = db.execute(
        "SELECT id, username, full_name FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if account is None:
        abort(404)

    if request.method == "POST":
        _validate_csrf_token()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if len(password) < 8:
            flash("Kata sandi minimal 8 karakter.", "error")
        elif password != confirm_password:
            flash("Konfirmasi kata sandi tidak cocok.", "error")
        else:
            with db:
                db.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(password), user_id),
                )
            flash(f"Kata sandi akun {account['username']} berhasil diganti.", "success")
            return redirect(url_for("admin.dashboard", _anchor="accounts"))

    if not session.get("admin_csrf_token"):
        session["admin_csrf_token"] = secrets.token_urlsafe(32)
    return render_template(
        "admin_reset_password.html",
        account=dict(account),
        csrf_token=session["admin_csrf_token"],
    )


@admin_bp.route("/accounts/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_account(user_id: int):
    _validate_csrf_token()
    db = get_db()
    target = db.execute(
        "SELECT id, username, is_active, is_admin, is_superadmin FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if target is None:
        abort(404)

    if target["is_active"] and (target["is_admin"] or target["is_superadmin"]):
        other_active_admins = db.execute(
            """
            SELECT COUNT(*) AS total
            FROM users
            WHERE id != ? AND (is_admin = 1 OR is_superadmin = 1) AND is_active = 1
            """,
            (user_id,),
        ).fetchone()["total"]
        if other_active_admins == 0:
            flash("Admin aktif terakhir tidak dapat dihapus.", "error")
            return redirect(url_for("admin.dashboard", _anchor="accounts"))

    with db:
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))

    if user_id == g.user["id"]:
        session.clear()
        flash("Akun Anda berhasil dihapus.", "success")
        return redirect(url_for("main.index", masuk=1))
    flash(f"Akun {target['username']} berhasil dihapus.", "success")
    return redirect(url_for("admin.dashboard", _anchor="accounts"))
