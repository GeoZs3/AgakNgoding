from flask import Blueprint, redirect, render_template, request, url_for
from database.connection import get_db
from services.plant_service import (
    get_adiwiyata_impact_stats,
    get_filter_tag_groups,
    get_plants_grouped_by_type,
)

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def portal():
    """
    Halaman pembuka Tree Portal (/) dengan pintu interaktif.
    Jika URL lama membawa parameter katalog (?q=..., ?inc=..., ?exc=..., ?masuk=1),
    arahkan otomatis ke /katalog agar seluruh tautan lama tetap kompatibel.
    """
    if (
        request.args.get("masuk") == "1"
        or request.args.get("q")
        or request.args.getlist("inc")
        or request.args.getlist("exc")
    ):
        return redirect(url_for("main.index", **request.args.to_dict(flat=False)))

    return render_template("portal.html")


@main_bp.route("/home")
def home():
    """
    Homepage utama Proyek Adiwiyata dengan statistik langsung dari database SQLite.
    """
    db = get_db()
    stats = get_adiwiyata_impact_stats(db)
    return render_template("home.html", stats=stats)


@main_bp.route("/katalog")
def index():
    """
    Halaman Katalog Tanaman (/katalog).
    Nama fungsi endpoint dipertahankan sebagai 'index' (main.index) agar seluruh
    tautan kembali dari detail.html, add_plant.html, dan auth.py tetap bekerja utuh.
    """
    db = get_db()
    search_query = request.args.get("q", "").strip()
    include_tags = [t.strip() for t in request.args.getlist("inc") if t.strip()]
    exclude_tags = [t.strip() for t in request.args.getlist("exc") if t.strip()]

    tag_groups = get_filter_tag_groups(db)
    grouped_plants = get_plants_grouped_by_type(
        db=db,
        search_query=search_query,
        include_tags=include_tags,
        exclude_tags=exclude_tags,
    )

    return render_template(
        "index.html",
        grouped_plants=grouped_plants,
        tag_groups=tag_groups,
        search_query=search_query,
        include_tags=include_tags,
        exclude_tags=exclude_tags,
        skip_intro=True,
    )