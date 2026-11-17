from flask import Blueprint, redirect, render_template, request, url_for
from database.connection import get_db
from services.auth_service import editor_required
from services.plant_service import (
    get_adiwiyata_impact_stats,
    get_catalog_filter_options,
    get_inventory_list_for_managers,
    search_catalog_plants,
)

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def portal():
    """Halaman pembuka Tree Portal (/) dengan pengalihan otomatis jika membawa query katalog lama."""
    if (
        request.args.get("masuk") == "1"
        or request.args.get("q")
        or request.args.get("sector")
        or request.args.get("type")
        or request.args.getlist("inc")
        or request.args.getlist("exc")
    ):
        return redirect(url_for("main.index", **request.args.to_dict(flat=False)))

    return render_template("portal.html")


@main_bp.route("/home")
def home():
    """Homepage utama Proyek Adiwiyata dengan statistik COUNT(*) dari SQLite."""
    db = get_db()
    stats = get_adiwiyata_impact_stats(db)
    return render_template("home.html", stats=stats)


@main_bp.route("/katalog")
def index():
    """
    Katalog Hybrid Pengunjung (/katalog):
    - Navigasi rak kategori (Jenis Tanaman) & Sektor independen
    - Regular Search & Drawer Advanced Search
    - Sorting (name_asc, name_desc, location, newest)
    - Active Filter Chips yang dapat dihapus secara individual
    """
    db = get_db()
    search_query = request.args.get("q", "").strip()
    sector_code = request.args.get("sector", "").strip()
    subsector_id = request.args.get("subsector", "").strip()
    type_code = request.args.get("type", "").strip()
    status = request.args.get("status", "").strip()
    family = request.args.get("family", "").strip()
    sort_by = request.args.get("sort", "name_asc").strip()
    if sort_by not in ("name_asc", "name_desc", "location", "newest"):
        sort_by = "name_asc"

    legacy_inc = [t.strip() for t in request.args.getlist("inc") if t.strip()]
    legacy_exc = [t.strip() for t in request.args.getlist("exc") if t.strip()]

    filter_options = get_catalog_filter_options(db)
    catalog_result = search_catalog_plants(
        db=db,
        search_query=search_query,
        sector_code=sector_code,
        subsector_id=subsector_id,
        type_code=type_code,
        status=status,
        family=family,
        sort_by=sort_by,
        legacy_inc=legacy_inc,
        legacy_exc=legacy_exc,
    )

    return render_template(
        "index.html",
        plants=catalog_result["plants"],
        total_count=catalog_result["total_count"],
        active_chips=catalog_result["active_chips"],
        filter_options=filter_options,
        search_query=search_query,
        selected_sector=sector_code,
        selected_subsector=subsector_id,
        selected_type=type_code,
        selected_status=status,
        selected_family=family,
        sort_by=sort_by,
    )


@main_bp.route("/inventaris")
@editor_required
def inventory():
    """
    Ruang Kerja Inventarisasi Khusus Pengurus (/inventaris):
    - Dilindungi @editor_required di backend
    - Fokus pada efisiensi administrasi, pencarian cepat, dan pemantauan kondisi individu
    """
    db = get_db()
    search_query = request.args.get("q", "").strip()
    sector_code = request.args.get("sector", "").strip()
    type_code = request.args.get("type", "").strip()
    status = request.args.get("status", "").strip()
    only_needs_split = request.args.get("split") == "1"

    filter_options = get_catalog_filter_options(db)
    items = get_inventory_list_for_managers(
        db=db,
        search_query=search_query,
        sector_code=sector_code,
        type_code=type_code,
        status=status,
        only_needs_split=only_needs_split,
    )

    return render_template(
        "inventory.html",
        items=items,
        filter_options=filter_options,
        search_query=search_query,
        selected_sector=sector_code,
        selected_type=type_code,
        selected_status=status,
        only_needs_split=only_needs_split,
    )