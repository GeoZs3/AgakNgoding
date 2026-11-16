import io
import logging
import socket
import uuid
from pathlib import Path
from PIL import Image, UnidentifiedImageError
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
from services.ai_taxonomy_service import (
    dispatch_ai_worker_for_pending_tasks,
    request_ai_task_retry,
)
from services.qr_service import generate_plant_qr_bytes
from services.plant_service import (
    create_plant_with_references,
    delete_plant_entry,
    get_form_cascading_metadata,
    get_plant_by_uid,
    is_photo_referenced_by_any_plant,
    update_plant_with_references,
    verify_plant_taxonomy,
)

plants_bp = Blueprint("plants", __name__, url_prefix="/tanaman")
logger = logging.getLogger(__name__)

FORMAT_TO_EXT = {
    "JPEG": "jpg",
    "PNG": "png",
    "WEBP": "webp",
}

EXT_TO_ALLOWED_FORMATS = {
    "jpg": {"JPEG"},
    "jpeg": {"JPEG"},
    "png": {"PNG"},
    "webp": {"WEBP"},
}


def validate_and_read_uploaded_photo(photo_file) -> tuple[bytes, str]:
    """
    Memvalidasi file foto berdasarkan:
    1. Keberadaan file & ekstensi awal.
    2. Batas ukuran file aktual (MAX_PHOTO_SIZE_BYTES).
    3. Konten biner gambar aktual menggunakan Pillow (bukan sekadar ekstensi/MIME header).
    4. Kesesuaian format biner asli (JPEG/PNG/WEBP) dengan ekstensi yang diizinkan.
    Mengembalikan tuple (raw_bytes, safe_normalized_extension).
    """
    if not photo_file or not photo_file.filename:
        raise ValueError("Foto tanaman wajib diunggah sebelum menyimpan data.")

    safe_original = secure_filename(photo_file.filename)
    if "." not in safe_original:
        raise ValueError("Nama file foto tidak memiliki ekstensi yang valid.")

    raw_ext = safe_original.rsplit(".", 1)[1].lower()
    allowed_exts = current_app.config.get("ALLOWED_EXTENSIONS", {"png", "jpg", "jpeg", "webp"})
    if raw_ext not in allowed_exts:
        raise ValueError("Ekstensi foto harus PNG, JPG, JPEG, atau WEBP.")

    max_size = int(current_app.config.get("MAX_PHOTO_SIZE_BYTES", 5 * 1024 * 1024))
    raw_bytes = photo_file.read(max_size + 1)
    if len(raw_bytes) == 0:
        raise ValueError("File foto kosong (0 byte).")
    if len(raw_bytes) > max_size:
        max_mb = max_size / (1024 * 1024)
        raise ValueError(f"Ukuran file foto melebihi batas maksimum {max_mb:.1f} MB.")

    # Verifikasi struktur biner gambar menggunakan Pillow
    try:
        with Image.open(io.BytesIO(raw_bytes)) as img_verify:
            detected_format = (img_verify.format or "").upper()
            img_verify.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ValueError("Konten file bukan gambar yang valid atau file rusak.") from exc

    allowed_formats = current_app.config.get("ALLOWED_IMAGE_FORMATS", {"JPEG", "PNG", "WEBP"})
    if detected_format not in allowed_formats:
        raise ValueError(f"Format gambar '{detected_format or 'tidak dikenal'}' tidak didukung. Gunakan JPEG, PNG, atau WEBP.")

    expected_formats = EXT_TO_ALLOWED_FORMATS.get(raw_ext, set())
    if detected_format not in expected_formats:
        raise ValueError("Ekstensi file tidak sesuai dengan isi gambar sebenarnya.")

    normalized_ext = FORMAT_TO_EXT[detected_format]
    return raw_bytes, normalized_ext


def _safe_delete_photo_file(db, upload_folder: Path, photo_filename: str) -> bool:
    """
    Menghapus file foto secara aman dari disk:
    - Memastikan path berada di dalam upload_folder (anti path traversal).
    - Memastikan tidak ada entri tanaman lain di DB yang masih memakai file ini.
    - Menangani kegagalan penghapusan file tanpa melempar exception.
    """
    if not photo_filename:
        return True

    if is_photo_referenced_by_any_plant(db, photo_filename):
        logger.info("File foto '%s' tidak dihapus karena masih digunakan entri lain.", photo_filename)
        return True

    base_dir = upload_folder.resolve()
    target_path = (upload_folder / photo_filename).resolve()
    if target_path.parent != base_dir:
        logger.warning("Percobaan akses path tidak valid ditolak untuk file '%s'.", photo_filename)
        return False

    try:
        if target_path.exists():
            target_path.unlink()
        return True
    except OSError as exc:
        logger.error("Orphaned photo file gagal dihapus (%s): %s", target_path, exc)
        return False


def _get_lan_ip() -> str:
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
    db = get_db()
    plant = get_plant_by_uid(db, uid)
    if plant is None:
        abort(404)

    detail_url = url_for("plants.detail", uid=uid, _external=True)
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
    """Memperbarui status (termasuk Mati), jenis tanaman, lokasi lintas sektor, dan catatan."""
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
        update_plant_with_references(
            db=db,
            uid=uid,
            status=status,
            plant_type_name=plant_type_name,
            plant_type_code=plant_type_code,
            sector_name=sector_name,
            sector_code=sector_code,
            subsector_name=subsector_name,
            subsector_code=subsector_code,
            notes=notes,
        )
        flash("Perubahan data tanaman berhasil disimpan.", "success")
    except Exception as exc:
        flash(f"Gagal memperbarui data: {exc}", "error")

    return redirect(url_for("plants.detail", uid=uid))


@plants_bp.route("/<string:uid>/taksonomi/verifikasi", methods=["POST"])
@editor_required
def verify_taxonomy_route(uid: str):
    """Memverifikasi atau menolak hasil taksonomi AI pada entri tanaman."""
    db = get_db()
    plant = get_plant_by_uid(db, uid)
    if plant is None:
        abort(404)

    action = request.form.get("action", "").strip()
    try:
        verify_plant_taxonomy(db, uid, action)
        flash("Status verifikasi taksonomi berhasil diperbarui.", "success")
    except Exception as exc:
        flash(f"Gagal memperbarui verifikasi taksonomi: {exc}", "error")

    return redirect(url_for("plants.detail", uid=uid))


@plants_bp.route("/<string:uid>/taksonomi/retry", methods=["POST"])
@editor_required
def retry_taxonomy_ai(uid: str):
    """Menjalankan ulang proses identifikasi taksonomi AI yang gagal."""
    db = get_db()
    plant = get_plant_by_uid(db, uid)
    if plant is None:
        abort(404)

    max_attempts = int(current_app.config.get("AI_MAX_RETRIES", 3))
    if request_ai_task_retry(db, uid, max_attempts=max_attempts):
        dispatch_ai_worker_for_pending_tasks(
            db_path=Path(current_app.config["DATABASE_PATH"]),
            gemini_api_key=current_app.config.get("GEMINI_API_KEY", ""),
            gemini_model=current_app.config.get("GEMINI_MODEL", "gemini-3.8-flash"),
            openai_api_key=current_app.config.get("OPENAI_API_KEY", ""),
            openai_model=current_app.config.get("OPENAI_MODEL", "gpt-4o-mini"),
        )
        flash("Identifikasi taksonomi AI dijadwalkan ulang.", "success")
    else:
        flash("Tugas AI sedang diproses atau tidak dalam status gagal.", "error")

    return redirect(url_for("plants.detail", uid=uid))


@plants_bp.route("/<string:uid>/hapus", methods=["POST"])
@editor_required
def delete_plant(uid: str):
    """
    Menghapus entri tanaman dengan urutan aman:
    1. Hapus record database dalam transaksi terlebih dahulu.
    2. Jika database berhasil dihapus, hapus file foto dari disk (jika tidak dipakai entri lain).
    3. Jika penghapusan file gagal, catat ke log dan tetap arahkan ke beranda dengan peringatan.
    """
    db = get_db()
    try:
        result = delete_plant_entry(db, uid)
    except Exception as exc:
        logger.error("Gagal menghapus record tanaman '%s' dari database: %s", uid, exc)
        flash("Gagal menghapus data tanaman dari database. File foto tetap dipertahankan.", "error")
        return redirect(url_for("plants.detail", uid=uid))

    if not result["deleted"]:
        abort(404)

    photo_filename = result["photo_filename"]
    if photo_filename and result["can_delete_photo"]:
        upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
        deleted_ok = _safe_delete_photo_file(db, upload_folder, photo_filename)
        if not deleted_ok:
            flash(
                "Entri tanaman berhasil dihapus dari database, namun file foto lama gagal dibersihkan dari penyimpanan.",
                "warning",
            )
            return redirect(url_for("main.index", masuk=1))

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

        # Aturan desain #3: Tanaman baru tidak boleh dibuat dengan status Mati
        if status == "Mati":
            flash("Tanaman baru tidak boleh dibuat dengan status Mati.", "error")
            return render_template("add_plant.html", metadata=metadata), 400

        if status not in ("Hidup", "Perawatan Khusus", "Layu"):
            status = "Hidup"

        if not name or not plant_type_name or not sector_name or not subsector_name or not manager_code:
            flash("Nama tanaman, jenis tanaman, sektor, subsektor, dan penanggung jawab (P) wajib diisi.", "error")
            return render_template("add_plant.html", metadata=metadata), 400

        # Validasi konten biner & ukuran foto sebelum menulis ke disk
        try:
            raw_photo_bytes, safe_ext = validate_and_read_uploaded_photo(request.files.get("photo"))
        except ValueError as val_err:
            flash(str(val_err), "error")
            return render_template("add_plant.html", metadata=metadata), 400

        upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
        upload_folder.mkdir(parents=True, exist_ok=True)
        photo_filename = f"{uuid.uuid4().hex}.{safe_ext}"
        save_path = upload_folder / photo_filename

        db_committed = False
        try:
            save_path.write_bytes(raw_photo_bytes)

            created = create_plant_with_references(
                db=db,
                name=name,
                quantity=1,
                status=status,
                plant_type_name=plant_type_name,
                plant_type_code=plant_type_code,
                sector_name=sector_name,
                sector_code=sector_code,
                subsector_name=subsector_name,
                subsector_code=subsector_code,
                manager_code=manager_code,
                photo_filename=photo_filename,
                notes=notes,
                created_by_user_id=g.user["id"] if g.get("user") else None,
                enqueue_ai_task=True,
                max_ai_attempts=int(current_app.config.get("AI_MAX_RETRIES", 3)),
            )
            db_committed = True

            dispatch_ai_worker_for_pending_tasks(
                db_path=Path(current_app.config["DATABASE_PATH"]),
                gemini_api_key=current_app.config.get("GEMINI_API_KEY", ""),
                gemini_model=current_app.config.get("GEMINI_MODEL", "gemini-3.8-flash"),
                openai_api_key=current_app.config.get("OPENAI_API_KEY", ""),
                openai_model=current_app.config.get("OPENAI_MODEL", "gpt-4o-mini"),
            )

            return redirect(url_for("plants.detail", uid=created["uid"], show_qr=1))
        except Exception as err:
            flash(f"Gagal menyimpan data tanaman: {err}", "error")
            return render_template("add_plant.html", metadata=metadata), 400
        finally:
            # Hapus foto yang baru diunggah hanya jika transaksi database belum commit dan tidak dipakai entri lain
            if not db_committed and save_path.exists():
                if not is_photo_referenced_by_any_plant(db, photo_filename):
                    try:
                        save_path.unlink()
                    except OSError as cleanup_err:
                        logger.error("Gagal membersihkan file foto sementara '%s': %s", save_path, cleanup_err)

    return render_template("add_plant.html", metadata=metadata)