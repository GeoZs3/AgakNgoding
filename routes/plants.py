import json
import uuid
from pathlib import Path
from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename
from database.connection import get_db
from services.auth_service import editor_required
from services.plant_service import (
    create_plant_entry,
    get_form_cascading_metadata,
    get_plant_by_uid,
)

plants_bp = Blueprint("plants", __name__, url_prefix="/tanaman")


def _allowed_file(filename: str) -> bool:
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in current_app.config["ALLOWED_EXTENSIONS"]


@plants_bp.route("/<string:uid>")
def detail(uid: str):
    db = get_db()
    plant = get_plant_by_uid(db, uid)
    if plant is None:
        abort(404)
    return render_template("detail.html", plant=plant)


@plants_bp.route("/tambah", methods=["GET", "POST"])
@editor_required
def add_plant():
    db = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        status = request.form.get("status", "Hidup").strip()
        notes = request.form.get("notes", "").strip()

        try:
            quantity = int(request.form.get("quantity", 1))
            plant_type_id = int(request.form.get("plant_type_id", 0))
            subsector_id = int(request.form.get("subsector_id", 0))
            manager_code = request.form.get("manager_code", "").strip().upper()
        except ValueError:
            flash("Input numerik atau pilihan referensi tidak valid.", "error")
            return redirect(url_for("plants.add_plant"))

        if not name or quantity < 0 or not plant_type_id or not subsector_id or not manager_code:
            flash("Nama tanaman, jumlah, jenis tanaman, subsektor, dan penanggung jawab (P) wajib diisi.", "error")
            return redirect(url_for("plants.add_plant"))

        # Jika user yang login adalah P pengurus tanaman, pastikan hanya menginput untuk kode P-nya
        if g.user["role"] == "p_manager" and g.user["manager_code"] != manager_code:
            flash(f"Akun Anda hanya berhak menambahkan data untuk wilayah {g.user['manager_code']}.", "error")
            return redirect(url_for("plants.add_plant"))

        photo_filename = None
        photo_file = request.files.get("photo")
        if photo_file and photo_file.filename:
            if not _allowed_file(photo_file.filename):
                flash("Format foto harus PNG, JPG, JPEG, atau WEBP.", "error")
                return redirect(url_for("plants.add_plant"))
            safe_name = secure_filename(photo_file.filename)
            ext = safe_name.rsplit(".", 1)[1].lower()
            photo_filename = f"{uuid.uuid4().hex}.{ext}"
            save_path = Path(current_app.config["UPLOAD_FOLDER"]) / photo_filename
            photo_file.save(save_path)

        taxonomy_data = {
            "kingdom": request.form.get("kingdom", "Plantae"),
            "division": request.form.get("division", ""),
            "class_name": request.form.get("class_name", ""),
            "order_name": request.form.get("order_name", ""),
            "family": request.form.get("family", ""),
            "genus": request.form.get("genus", ""),
            "species": request.form.get("species", ""),
            "scientific_name": request.form.get("scientific_name", ""),
        }

        try:
            created = create_plant_entry(
                db=db,
                name=name,
                quantity=quantity,
                status=status,
                plant_type_id=plant_type_id,
                subsector_id=subsector_id,
                manager_code=manager_code,
                taxonomy_data=taxonomy_data,
                photo_filename=photo_filename,
                notes=notes,
                created_by_user_id=g.user["id"],
            )
            flash(f"Tanaman berhasil ditambahkan dengan ID: {created['plant_code']}", "success")
            return redirect(url_for("plants.detail", uid=created["uid"]))
        except Exception as exc:
            flash(f"Gagal menyimpan data tanaman: {exc}", "error")

    metadata = get_form_cascading_metadata(db)
    return render_template(
        "add_plant.html",
        metadata=metadata,
        metadata_json=json.dumps(metadata),
    )