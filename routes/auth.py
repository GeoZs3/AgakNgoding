from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from database.connection import get_db
from services.auth_service import authenticate_user

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user") is not None:
        return redirect(url_for("main.inventory"))

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
            return redirect(url_for("main.inventory"))

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Anda telah keluar dari sesi pengurus.", "success")
    return redirect(url_for("main.home"))