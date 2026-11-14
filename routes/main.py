from flask import Blueprint, render_template, request
from database.connection import get_db
from services.plant_service import get_filter_tag_groups, get_plants_grouped_by_type

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    db = get_db()
    search_query = request.args.get("q", "").strip()
    include_tags = [t.strip() for t in request.args.getlist("inc") if t.strip()]
    exclude_tags = [t.strip() for t in request.args.getlist("exc") if t.strip()]

    skip_intro = (
        request.args.get("masuk") == "1"
        or bool(search_query)
        or bool(include_tags)
        or bool(exclude_tags)
    )

    grouped_plants = get_plants_grouped_by_type(
        db=db,
        search_query=search_query,
        include_tags=include_tags,
        exclude_tags=exclude_tags,
    )
    tag_groups = get_filter_tag_groups(db)

    return render_template(
        "index.html",
        grouped_plants=grouped_plants,
        tag_groups=tag_groups,
        include_tags=include_tags,
        exclude_tags=exclude_tags,
        search_query=search_query,
        skip_intro=skip_intro,
    )