import secrets
from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for
from database.connection import get_db
from services.auth_service import authenticate_user
from werkzeug.security import check_password_hash, generate_password_hash

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user") is not None:
        if g.user["is_admin"] or g.user["is_superadmin"]:
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("plants.add_plant"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        db = get_db()

        user = authenticate_user(db, username, password)
        if user is None:
            flash("Username atau kata sandi salah, atau akun tidak memiliki hak pengurus tanaman.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Selamat datang, {user['full_name']}.", "success")
            if user["is_admin"] or user["is_superadmin"]:
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("plants.add_plant"))

    return render_template("login.html")


@auth_bp.route("/account/password", methods=["GET", "POST"])
def change_password():
    if g.get("user") is None:
        flash("Silakan login untuk mengganti kata sandi.", "error")
        return redirect(url_for("auth.login"))

    if not session.get("password_csrf_token"):
        session["password_csrf_token"] = secrets.token_urlsafe(32)

    if request.method == "POST":
        expected = session.get("password_csrf_token", "")
        submitted = request.form.get("_csrf_token", "")
        if not expected or not secrets.compare_digest(expected, submitted):
            abort(400)

        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        db = get_db()
        row = db.execute(
            "SELECT password_hash FROM users WHERE id = ? AND is_active = 1",
            (g.user["id"],),
        ).fetchone()

        if row is None or not check_password_hash(row["password_hash"], current_password):
            flash("Kata sandi saat ini salah.", "error")
        elif len(new_password) < 8:
            flash("Kata sandi baru minimal 8 karakter.", "error")
        elif new_password != confirm_password:
            flash("Konfirmasi kata sandi baru tidak cocok.", "error")
        elif check_password_hash(row["password_hash"], new_password):
            flash("Kata sandi baru harus berbeda dari kata sandi saat ini.", "error")
        else:
            with db:
                db.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(new_password), g.user["id"]),
                )
            flash("Kata sandi berhasil diganti.", "success")
            return redirect(url_for("auth.change_password"))

    return render_template(
        "account_password.html",
        csrf_token=session["password_csrf_token"],
    )


@auth_bp.route("/logout")
def logout():
    presence_id = session.get("presence_id")
    if presence_id:
        with get_db() as db:
            db.execute(
                "DELETE FROM active_sessions WHERE session_id = ?",
                (presence_id,),
            )
    session.clear()
    flash("Anda telah keluar dari sesi pengurus.", "success")
    return redirect(url_for("main.index", masuk=1))


@auth_bp.route("/presence", methods=["POST"])
def presence():
    if g.get("user") is None:
        return {"error": "Login diperlukan."}, 401
    return "", 204