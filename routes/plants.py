import socket
import uuid
from pathlib import Path
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.utils import secure_filename
from database.connection import get_db
from services.auth_service import editor_required
from services.ai_taxonomy_service import attach_taxonomy_in_background
from services.qr_service import generate_plant_qr_bytes
from services.plant_service import (
    create_plant_entry,
    delete_plant_entry,
    get_form_cascading_metadata,
    get_or_create_plant_type,
    get_or_create_sector,
    get_or_create_subsector,
    get_plant_by_uid,
    update_plant_entry,
)

plants_bp = Blueprint("plants", __name__, url_prefix="/tanaman")


def _allowed_file(filename: str) -> bool:
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in current_app.config["ALLOWED_EXTENSIONS"]


def _get_lan_ip() -> str:
    """Mendeteksi alamat IP Wi-Fi/LAN lokal komputer jika diakses via localhost/127.0.0.1."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


@plants_bp.route("/<string:uid>")
def detail(uid: str):
    db = get_db()
    plant = get_plant_by_uid(db, uid)
    if plant is None:
        abort(404)

    show_qr_modal = request.args.get("show_qr") == "1"
    metadata = get_form_cascading_metadata(db) if g.get("user") else None

    return render_template(
        "detail.html",
        plant=plant,
        show_qr_modal=show_qr_modal,
        metadata=metadata,
    )


@plants_bp.route("/<string:uid>/qr.png")
def dynamic_qr(uid: str):
    """
    Menghasilkan QR Code on-the-fly berdasarkan host/IP saat ini.
    Tidak ada file QR yang disimpan di server; URL selalu sinkron dengan IPv4/domain aktif.
    """
    db = get_db()
    plant = get_plant_by_uid(db, uid)
    if plant is None:
        abort(404)

    detail_url = url_for("plants.detail", uid=uid, _external=True)
    # Jika diakses dari laptop memakai localhost/127.0.0.1, ganti otomatis ke IPv4 Wi-Fi aktif
    if "127.0.0.1" in detail_url or "localhost" in detail_url:
        lan_ip = _get_lan_ip()
        detail_url = detail_url.replace("127.0.0.1", lan_ip).replace("localhost", lan_ip)

    logo_path = Path(current_app.root_path) / "static" / "logo_sekolah.png"
    qr_buffer = generate_plant_qr_bytes(target_url=detail_url, logo_path=logo_path)

    as_download = request.args.get("download") == "1"
    return send_file(
        qr_buffer,
        mimetype="image/png",
        as_attachment=as_download,
        download_name=f"QR_{plant['plant_code']}.png",
    )


@plants_bp.route("/<string:uid>/edit", methods=["POST"])
@editor_required
def edit_plant(uid: str):
    """Memperbarui status, jenis tanaman, lokasi (sektor/subsektor), dan catatan (khusus Guru & P)."""
    db = get_db()
    plant = get_plant_by_uid(db, uid)
    if plant is None:
        abort(404)

    status = request.form.get("status", "Hidup").strip()
    plant_type_name = request.form.get("plant_type_name", "").strip()
    plant_type_code = request.form.get("plant_type_code", "").strip()
    sector_name = request.form.get("sector_name", "").strip()
    sector_code = request.form.get("sector_code", "").strip()
    subsector_name = request.form.get("subsector_name", "").strip()
    subsector_code = request.form.get("subsector_code", "").strip()
    notes = request.form.get("notes", "").strip()

    if status not in ("Hidup", "Perawatan Khusus", "Layu", "Mati"):
        status = "Hidup"

    if not plant_type_name or not sector_name or not subsector_name:
        flash("Jenis tanaman, sektor, dan subsektor wajib diisi.", "error")
        return redirect(url_for("plants.detail", uid=uid))

    try:
        with db:
            plant_type_id = get_or_create_plant_type(db, plant_type_name, plant_type_code)
            sector_id = get_or_create_sector(db, sector_name, sector_code)
            subsector_id = get_or_create_subsector(db, sector_id, subsector_name, subsector_code)

        update_plant_entry(
            db=db,
            uid=uid,
            status=status,
            plant_type_id=plant_type_id,
            subsector_id=subsector_id,
            notes=notes,
        )
        flash("Perubahan data tanaman berhasil disimpan.", "success")
    except Exception as exc:
        flash(f"Gagal memperbarui data: {exc}", "error")

    return redirect(url_for("plants.detail", uid=uid))


@plants_bp.route("/<string:uid>/hapus", methods=["POST"])
@editor_required
def delete_plant(uid: str):
    """Menghapus entri tanaman beserta file fotonya (khusus Guru & P)."""
    db = get_db()
    photo_filename = delete_plant_entry(db, uid)
    if photo_filename is None:
        abort(404)

    if photo_filename:
        photo_path = Path(current_app.config["UPLOAD_FOLDER"]) / photo_filename
        photo_path.unlink(missing_ok=True)

    flash("Entri tanaman berhasil dihapus dari arsip.", "success")
    return redirect(url_for("main.index", masuk=1))


@plants_bp.route("/tambah", methods=["GET", "POST"])
@editor_required
def add_plant():
    db = get_db()
    metadata = get_form_cascading_metadata(db)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        plant_type_name = request.form.get("plant_type_name", "").strip()
        plant_type_code = request.form.get("plant_type_code", "").strip()
        sector_name = request.form.get("sector_name", "").strip()
        sector_code = request.form.get("sector_code", "").strip()
        subsector_name = request.form.get("subsector_name", "").strip()
        subsector_code = request.form.get("subsector_code", "").strip()
        manager_code = request.form.get("manager_code", "").strip()
        status = request.form.get("status", "Hidup").strip()
        notes = request.form.get("notes", "").strip()

        if status not in ("Hidup", "Perawatan Khusus", "Layu"):
            status = "Hidup"

        if not name or not plant_type_name or not sector_name or not subsector_name or not manager_code:
            flash("Nama tanaman, jenis tanaman, sektor, subsektor, dan penanggung jawab (P) wajib diisi.", "error")
            return render_template("add_plant.html", metadata=metadata)

        photo_file = request.files.get("photo")
        if not photo_file or not photo_file.filename:
            flash("Foto tanaman wajib diunggah sebelum menyimpan data.", "error")
            return render_template("add_plant.html", metadata=metadata)

        if not _allowed_file(photo_file.filename):
            flash("Format foto harus PNG, JPG, JPEG, atau WEBP.", "error")
            return render_template("add_plant.html", metadata=metadata)

        safe_name = secure_filename(photo_file.filename)
        ext = safe_name.rsplit(".", 1)[1].lower()
        photo_filename = f"{uuid.uuid4().hex}.{ext}"
        save_path = Path(current_app.config["UPLOAD_FOLDER"]) / photo_filename
        photo_file.save(save_path)

        try:
            with db:
                plant_type_id = get_or_create_plant_type(db, plant_type_name, plant_type_code)
                sector_id = get_or_create_sector(db, sector_name, sector_code)
                subsector_id = get_or_create_subsector(db, sector_id, subsector_name, subsector_code)

            created = create_plant_entry(
                db=db,
                name=name,
                quantity=1,
                status=status,
                plant_type_id=plant_type_id,
                subsector_id=subsector_id,
                manager_code=manager_code,
                taxonomy_data={},
                photo_filename=photo_filename,
                notes=notes,
                created_by_user_id=g.user["id"] if g.get("user") else None,
            )

            uid = created["uid"]

            attach_taxonomy_in_background(
                db_path=Path(current_app.config["DATABASE_PATH"]),
                plant_uid=uid,
                plant_name=name,
                gemini_api_key=current_app.config.get("GEMINI_API_KEY", ""),
                gemini_model=current_app.config.get("GEMINI_MODEL", "gemini-3.8-flash"),
                openai_api_key=current_app.config.get("OPENAI_API_KEY", ""),
                openai_model=current_app.config.get("OPENAI_MODEL", "gpt-4o-mini"),
            )

            return redirect(url_for("plants.detail", uid=uid, show_qr=1))
        except Exception as err:
            if save_path.exists():
                save_path.unlink(missing_ok=True)
            flash(f"Gagal menyimpan data tanaman: {err}", "error")

    return render_template("add_plant.html", metadata=metadata)