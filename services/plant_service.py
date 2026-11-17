import re
import uuid
import sqlite3
from collections import defaultdict
from typing import Any, Dict, List, Optional


def generate_plant_uid() -> str:
    """Menghasilkan UID permanen berbasis UUIDv4 untuk identitas internal backend."""
    return str(uuid.uuid4())


def _generate_short_code(label: str, max_len: int = 5) -> str:
    """Membuat singkatan kode otomatis dari nama jika pengguna tidak mengisi kode manual."""
    words = re.findall(r"[A-Za-z0-9]+", label.upper())
    if not words:
        return "NEW"
    if len(words) == 1:
        return words[0][:max_len]
    initials = "".join(w[0] for w in words[:max_len])
    return initials if len(initials) >= 2 else words[0][:max_len]


def get_or_create_sector(db: sqlite3.Connection, sector_name: str, sector_code: str = "") -> int:
    clean_name = sector_name.strip()
    existing = db.execute(
        "SELECT id FROM sectors WHERE LOWER(name) = LOWER(?)", (clean_name,)
    ).fetchone()
    if existing:
        return int(existing["id"])

    base_code = sector_code.strip().upper() or _generate_short_code(clean_name, 4)
    final_code = base_code
    counter = 1
    while db.execute("SELECT 1 FROM sectors WHERE code = ?", (final_code,)).fetchone():
        counter += 1
        final_code = f"{base_code}{counter}"

    cur = db.execute(
        "INSERT INTO sectors (code, name) VALUES (?, ?)", (final_code, clean_name)
    )
    return int(cur.lastrowid)


def get_or_create_subsector(
    db: sqlite3.Connection, sector_id: int, subsector_name: str, subsector_code: str = ""
) -> int:
    clean_name = subsector_name.strip()
    existing = db.execute(
        "SELECT id FROM subsectors WHERE sector_id = ? AND LOWER(name) = LOWER(?)",
        (sector_id, clean_name),
    ).fetchone()
    if existing:
        return int(existing["id"])

    base_code = subsector_code.strip().upper() or _generate_short_code(clean_name, 5)
    final_code = base_code
    counter = 1
    while db.execute(
        "SELECT 1 FROM subsectors WHERE sector_id = ? AND code = ?", (sector_id, final_code)
    ).fetchone():
        counter += 1
        final_code = f"{base_code}{counter}"

    cur = db.execute(
        "INSERT INTO subsectors (sector_id, code, name) VALUES (?, ?, ?)",
        (sector_id, final_code, clean_name),
    )
    return int(cur.lastrowid)


def get_or_create_plant_type(
    db: sqlite3.Connection, type_name: str, type_code: str = ""
) -> int:
    clean_name = type_name.strip()
    existing = db.execute(
        "SELECT id FROM plant_types WHERE LOWER(name) = LOWER(?)", (clean_name,)
    ).fetchone()
    if existing:
        return int(existing["id"])

    base_code = type_code.strip().upper() or _generate_short_code(clean_name, 5)
    final_code = base_code
    counter = 1
    while db.execute("SELECT 1 FROM plant_types WHERE code = ?", (final_code,)).fetchone():
        counter += 1
        final_code = f"{base_code}{counter}"

    cur = db.execute(
        "INSERT INTO plant_types (code, name) VALUES (?, ?)", (final_code, clean_name)
    )
    return int(cur.lastrowid)


def get_next_subsector_sequence(db: sqlite3.Connection, subsector_id: int) -> int:
    row = db.execute(
        "SELECT COALESCE(MAX(subsector_seq), 0) + 1 AS next_seq FROM plants WHERE subsector_id = ?",
        (subsector_id,),
    ).fetchone()
    return int(row["next_seq"]) if row else 1


def build_public_plant_id(
    sector_code: str,
    subsector_code: str,
    subsector_seq: int,
    plant_type_code: str,
    manager_code: str,
) -> str:
    seq_formatted = f"{subsector_seq:03d}"
    return (
        f"{sector_code.upper()}-"
        f"{subsector_code.upper()}-"
        f"{seq_formatted}-"
        f"{plant_type_code.upper()}-"
        f"{manager_code.upper()}"
    )


def _insert_plant_record(
    db: sqlite3.Connection,
    name: str,
    quantity: int,
    status: str,
    plant_type_id: int,
    subsector_id: int,
    manager_code: str,
    taxonomy_data: Dict[str, str],
    photo_filename: Optional[str] = None,
    notes: Optional[str] = None,
    description: Optional[str] = None,
    characteristics: Optional[str] = None,
    ecological_benefits: Optional[str] = None,
    created_by_user_id: Optional[int] = None,
    taxonomy_status: str = "verified",
) -> Dict[str, str]:
    """Helper internal penulisan 1 individu tanaman (quantity selalu dikunci ke 1)."""
    loc_row = db.execute(
        """
        SELECT s.id AS sector_id, s.code AS sector_code, sub.code AS subsector_code
        FROM subsectors sub
        INNER JOIN sectors s ON sub.sector_id = s.id
        WHERE sub.id = ?
        """,
        (subsector_id,),
    ).fetchone()
    if not loc_row:
        raise ValueError("Subsektor tidak valid.")

    type_row = db.execute(
        "SELECT code FROM plant_types WHERE id = ?", (plant_type_id,)
    ).fetchone()
    if not type_row:
        raise ValueError("Jenis tanaman tidak valid.")

    mgr_row = db.execute(
        "SELECT code FROM managers WHERE code = ? AND is_plant_manager = 1",
        (manager_code,),
    ).fetchone()
    if not mgr_row:
        raise ValueError("Kode penanggung jawab (P) tidak valid atau bukan pengurus tanaman.")

    taxonomy_id: Optional[int] = None
    family = (taxonomy_data.get("family") or "").strip() or None
    genus = (taxonomy_data.get("genus") or "").strip() or None
    species = (taxonomy_data.get("species") or "").strip() or None
    scientific_name = (taxonomy_data.get("scientific_name") or "").strip() or None
    division = (taxonomy_data.get("division") or "").strip() or None
    class_name = (taxonomy_data.get("class_name") or "").strip() or None
    order_name = (taxonomy_data.get("order_name") or "").strip() or None
    kingdom = (taxonomy_data.get("kingdom") or "Plantae").strip() or "Plantae"

    if any([family, genus, species, scientific_name, division, class_name, order_name]):
        if scientific_name and taxonomy_status == "verified":
            existing_tx = db.execute(
                """
                SELECT id FROM plant_taxonomy
                WHERE LOWER(scientific_name) = LOWER(?) AND verification_status = 'verified'
                LIMIT 1
                """,
                (scientific_name,),
            ).fetchone()
            if existing_tx:
                taxonomy_id = int(existing_tx["id"])

        if taxonomy_id is None:
            cur_tx = db.execute(
                """
                INSERT INTO plant_taxonomy
                    (kingdom, division, class_name, order_name, family, genus, species, scientific_name, verification_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kingdom,
                    division,
                    class_name,
                    order_name,
                    family,
                    genus,
                    species,
                    scientific_name,
                    taxonomy_status,
                ),
            )
            taxonomy_id = int(cur_tx.lastrowid)

    uid = generate_plant_uid()
    subsector_seq = get_next_subsector_sequence(db, subsector_id)
    plant_code = build_public_plant_id(
        sector_code=loc_row["sector_code"],
        subsector_code=loc_row["subsector_code"],
        subsector_seq=subsector_seq,
        plant_type_code=type_row["code"],
        manager_code=mgr_row["code"],
    )

    individual_quantity = 1

    db.execute(
        """
        INSERT INTO plants (
            uid, plant_code, subsector_seq, name, quantity, status,
            plant_type_id, taxonomy_id, subsector_id, manager_code,
            photo_filename, description, characteristics, ecological_benefits,
            notes, created_by_user_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uid,
            plant_code,
            subsector_seq,
            name.strip(),
            individual_quantity,
            status.strip(),
            plant_type_id,
            taxonomy_id,
            subsector_id,
            mgr_row["code"],
            photo_filename,
            (description or "").strip() or None,
            (characteristics or "").strip() or None,
            (ecological_benefits or "").strip() or None,
            (notes or "").strip() or None,
            created_by_user_id,
        ),
    )

    return {"uid": uid, "plant_code": plant_code}


def create_plant_with_references(
    db: sqlite3.Connection,
    name: str,
    quantity: int,
    status: str,
    plant_type_name: str,
    plant_type_code: str,
    sector_name: str,
    sector_code: str,
    subsector_name: str,
    subsector_code: str,
    manager_code: str,
    photo_filename: Optional[str] = None,
    notes: Optional[str] = None,
    description: Optional[str] = None,
    characteristics: Optional[str] = None,
    ecological_benefits: Optional[str] = None,
    created_by_user_id: Optional[int] = None,
    enqueue_ai_task: bool = True,
    max_ai_attempts: int = 3,
) -> Dict[str, str]:
    """
    Menjalankan pembuatan referensi, entri 1 individu tanaman,
    dan tugas antrean taksonomi AI dalam SATU transaksi SQLite atomik tunggal.
    """
    with db:
        plant_type_id = get_or_create_plant_type(db, plant_type_name, plant_type_code)
        sector_id = get_or_create_sector(db, sector_name, sector_code)
        subsector_id = get_or_create_subsector(db, sector_id, subsector_name, subsector_code)

        created = _insert_plant_record(
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
            description=description,
            characteristics=characteristics,
            ecological_benefits=ecological_benefits,
            created_by_user_id=created_by_user_id,
        )

        if enqueue_ai_task:
            db.execute(
                """
                INSERT INTO ai_taxonomy_tasks (plant_uid, plant_name, status, attempt_count, max_attempts)
                VALUES (?, ?, 'pending', 0, ?)
                """,
                (created["uid"], name.strip(), max_ai_attempts),
            )

    return created


def create_plant_entry(
    db: sqlite3.Connection,
    name: str,
    quantity: int,
    status: str,
    plant_type_id: int,
    subsector_id: int,
    manager_code: str,
    taxonomy_data: Dict[str, str],
    photo_filename: Optional[str] = None,
    notes: Optional[str] = None,
    description: Optional[str] = None,
    characteristics: Optional[str] = None,
    ecological_benefits: Optional[str] = None,
    created_by_user_id: Optional[int] = None,
) -> Dict[str, str]:
    with db:
        return _insert_plant_record(
            db=db,
            name=name,
            quantity=1,
            status=status,
            plant_type_id=plant_type_id,
            subsector_id=subsector_id,
            manager_code=manager_code,
            taxonomy_data=taxonomy_data,
            photo_filename=photo_filename,
            notes=notes,
            description=description,
            characteristics=characteristics,
            ecological_benefits=ecological_benefits,
            created_by_user_id=created_by_user_id,
        )


def is_photo_referenced_by_any_plant(db: sqlite3.Connection, photo_filename: str) -> bool:
    if not photo_filename:
        return False
    row = db.execute(
        "SELECT 1 FROM plants WHERE photo_filename = ? LIMIT 1",
        (photo_filename,),
    ).fetchone()
    return row is not None


def get_catalog_filter_options(db: sqlite3.Connection) -> Dict[str, Any]:
    """
    Mengambil opsi filter independen untuk katalog pengunjung.
    Hanya menampilkan sektor, subsektor, dan jenis tanaman yang memiliki minimal 1 entri (plant_count > 0).
    """
    sectors = [
        dict(r)
        for r in db.execute(
            """
            SELECT s.id, s.code, s.name, COUNT(p.uid) AS plant_count
            FROM sectors s
            INNER JOIN subsectors sub ON sub.sector_id = s.id
            INNER JOIN plants p ON p.subsector_id = sub.id
            GROUP BY s.id, s.code, s.name
            HAVING COUNT(p.uid) > 0
            ORDER BY s.name ASC
            """
        )
    ]

    subsectors = [
        dict(r)
        for r in db.execute(
            """
            SELECT sub.id, sub.sector_id, sub.code, sub.name, s.code AS sector_code, s.name AS sector_name, COUNT(p.uid) AS plant_count
            FROM subsectors sub
            INNER JOIN sectors s ON sub.sector_id = s.id
            INNER JOIN plants p ON p.subsector_id = sub.id
            GROUP BY sub.id, sub.sector_id, sub.code, sub.name, s.code, s.name
            HAVING COUNT(p.uid) > 0
            ORDER BY s.name ASC, sub.name ASC
            """
        )
    ]

    plant_types = [
        dict(r)
        for r in db.execute(
            """
            SELECT pt.id, pt.code, pt.name, COUNT(p.uid) AS plant_count
            FROM plant_types pt
            INNER JOIN plants p ON p.plant_type_id = pt.id
            GROUP BY pt.id, pt.code, pt.name
            HAVING COUNT(p.uid) > 0
            ORDER BY pt.name ASC
            """
        )
    ]

    families = [
        r["family"]
        for r in db.execute(
            """
            SELECT DISTINCT tx.family
            FROM plant_taxonomy tx
            INNER JOIN plants p ON p.taxonomy_id = tx.id
            WHERE tx.family IS NOT NULL AND tx.family != ''
            ORDER BY tx.family ASC
            """
        )
    ]

    statuses = ["Hidup", "Perawatan Khusus", "Layu", "Mati"]

    return {
        "sectors": sectors,
        "subsectors": subsectors,
        "plant_types": plant_types,
        "statuses": statuses,
        "families": families,
    }


def search_catalog_plants(
    db: sqlite3.Connection,
    search_query: str = "",
    sector_code: str = "",
    subsector_id: str = "",
    type_code: str = "",
    status: str = "",
    family: str = "",
    sort_by: str = "name_asc",
    legacy_inc: Optional[List[str]] = None,
    legacy_exc: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Kueri katalog hybrid pengunjung dengan:
    - Regular search (nama umum, nama ilmiah, kode tanaman, UID)
    - Advanced filter independen (sektor, subsektor, jenis tanaman, status, famili)
    - Sorting berbasis database (name_asc, name_desc, location, newest)
    - Active filter chips metadata yang dapat dilepas satuan
    """
    conditions: List[str] = []
    params: List[Any] = []
    active_chips: List[Dict[str, str]] = []

    q = search_query.strip()
    if q:
        conditions.append(
            "(p.name LIKE ? OR tx.scientific_name LIKE ? OR p.plant_code LIKE ? OR p.uid LIKE ?)"
        )
        like_q = f"%{q}%"
        params.extend([like_q, like_q, like_q, like_q])
        active_chips.append({"param": "q", "label": f"Cari: \"{q}\""})

    sec = sector_code.strip()
    if sec:
        sec_row = db.execute(
            "SELECT code, name FROM sectors WHERE LOWER(code) = LOWER(?)", (sec,)
        ).fetchone()
        if sec_row:
            conditions.append("s.code = ?")
            params.append(sec_row["code"])
            active_chips.append({"param": "sector", "label": f"Sektor: {sec_row['name']}"})

    sub_str = subsector_id.strip()
    if sub_str.isdigit():
        sub_row = db.execute(
            """
            SELECT sub.id, sub.name, s.name AS sector_name
            FROM subsectors sub
            INNER JOIN sectors s ON sub.sector_id = s.id
            WHERE sub.id = ?
            """,
            (int(sub_str),),
        ).fetchone()
        if sub_row:
            conditions.append("sub.id = ?")
            params.append(int(sub_row["id"]))
            active_chips.append({
                "param": "subsector",
                "label": f"Lokasi: {sub_row['sector_name']} - {sub_row['name']}",
            })

    t_code = type_code.strip()
    if t_code:
        type_row = db.execute(
            "SELECT code, name FROM plant_types WHERE LOWER(code) = LOWER(?)", (t_code,)
        ).fetchone()
        if type_row:
            conditions.append("pt.code = ?")
            params.append(type_row["code"])
            active_chips.append({"param": "type", "label": f"Jenis: {type_row['name']}"})

    st = status.strip()
    if st:
        conditions.append("p.status = ?")
        params.append(st)
        active_chips.append({"param": "status", "label": f"Kondisi: {st}"})

    fam = family.strip()
    if fam:
        conditions.append("tx.family = ?")
        params.append(fam)
        active_chips.append({"param": "family", "label": f"Famili: {fam}"})

    for tag in (legacy_inc or []):
        if ":" in tag:
            cat, val = tag.split(":", 1)
            if cat == "sector" and not sec:
                conditions.append("s.code = ?")
                params.append(val)
                active_chips.append({"param": "sector", "label": f"Sektor: {val}"})
            elif cat == "type" and not t_code:
                conditions.append("pt.code = ?")
                params.append(val)
                active_chips.append({"param": "type", "label": f"Jenis: {val}"})
            elif cat == "status" and not st:
                conditions.append("p.status = ?")
                params.append(val)
                active_chips.append({"param": "status", "label": f"Kondisi: {val}"})
            elif cat == "family" and not fam:
                conditions.append("tx.family = ?")
                params.append(val)
                active_chips.append({"param": "family", "label": f"Famili: {val}"})

    for tag in (legacy_exc or []):
        if ":" in tag:
            cat, val = tag.split(":", 1)
            if cat == "status":
                conditions.append("(p.status IS NULL OR p.status != ?)")
                params.append(val)
            elif cat == "sector":
                conditions.append("(s.code IS NULL OR s.code != ?)")
                params.append(val)
            elif cat == "type":
                conditions.append("(pt.code IS NULL OR pt.code != ?)")
                params.append(val)

    sort_map = {
        "name_asc": "p.name ASC, p.plant_code ASC",
        "name_desc": "p.name DESC, p.plant_code ASC",
        "location": "s.name ASC, sub.name ASC, p.subsector_seq ASC",
        "newest": "p.created_at DESC, p.plant_code DESC",
    }
    order_by_sql = sort_map.get(sort_by, sort_map["name_asc"])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT
            p.uid,
            p.plant_code,
            p.name,
            p.status,
            p.photo_filename,
            p.created_at,
            pt.code AS plant_type_code,
            pt.name AS plant_type_name,
            tx.scientific_name,
            tx.family,
            s.code AS sector_code,
            s.name AS sector_name,
            sub.name AS subsector_name
        FROM plants p
        INNER JOIN plant_types pt ON p.plant_type_id = pt.id
        INNER JOIN subsectors sub ON p.subsector_id = sub.id
        INNER JOIN sectors s ON sub.sector_id = s.id
        LEFT JOIN plant_taxonomy tx ON p.taxonomy_id = tx.id
        {where_clause}
        ORDER BY {order_by_sql}
    """
    plants = [dict(r) for r in db.execute(query, params).fetchall()]

    return {
        "plants": plants,
        "total_count": len(plants),
        "active_chips": active_chips,
    }


def get_filter_tag_groups(db: sqlite3.Connection) -> Dict[str, List[Dict[str, str]]]:
    """Dipertahankan untuk kompatibilitas modul lama."""
    opts = get_catalog_filter_options(db)
    return {
        "Status Hidup": [{"key": f"status:{st}", "label": st} for st in opts["statuses"]],
        "Lokasi (Sektor)": [
            {"key": f"sector:{s['code']}", "label": f"{s['name']} ({s['code']})"}
            for s in opts["sectors"]
        ],
        "Jenis Tanaman": [
            {"key": f"type:{t['code']}", "label": f"{t['name']} ({t['code']})"}
            for t in opts["plant_types"]
        ],
        "Taksonomi (Famili)": [{"key": f"family:{f}", "label": f} for f in opts["families"]],
    }


def get_plants_grouped_by_type(
    db: sqlite3.Connection,
    search_query: str = "",
    include_tags: Optional[List[str]] = None,
    exclude_tags: Optional[List[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Dipertahankan untuk kompatibilitas modul lama."""
    res = search_catalog_plants(
        db=db,
        search_query=search_query,
        legacy_inc=include_tags,
        legacy_exc=exclude_tags,
    )
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in res["plants"]:
        grouped[item["plant_type_name"]].append(item)
    return dict(grouped)


def get_inventory_list_for_managers(
    db: sqlite3.Connection,
    search_query: str = "",
    sector_code: str = "",
    type_code: str = "",
    status: str = "",
    only_needs_split: bool = False,
) -> List[Dict[str, Any]]:
    """Mengambil daftar lengkap inventaris individual khusus ruang kerja pengurus."""
    conditions: List[str] = []
    params: List[Any] = []

    q = search_query.strip()
    if q:
        conditions.append("(p.name LIKE ? OR p.plant_code LIKE ? OR p.uid LIKE ? OR sub.name LIKE ?)")
        like_q = f"%{q}%"
        params.extend([like_q, like_q, like_q, like_q])

    if sector_code.strip():
        conditions.append("s.code = ?")
        params.append(sector_code.strip())

    if type_code.strip():
        conditions.append("pt.code = ?")
        params.append(type_code.strip())

    if status.strip():
        conditions.append("p.status = ?")
        params.append(status.strip())

    if only_needs_split:
        conditions.append("p.needs_individual_split = 1")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT
            p.uid,
            p.plant_code,
            p.name,
            p.quantity,
            p.needs_individual_split,
            p.status,
            p.photo_filename,
            p.created_at,
            pt.code AS plant_type_code,
            pt.name AS plant_type_name,
            s.code AS sector_code,
            s.name AS sector_name,
            sub.name AS subsector_name,
            m.code AS manager_code,
            m.name AS manager_name,
            ai.status AS ai_task_status,
            tx.verification_status AS taxonomy_verification_status
        FROM plants p
        INNER JOIN plant_types pt ON p.plant_type_id = pt.id
        INNER JOIN subsectors sub ON p.subsector_id = sub.id
        INNER JOIN sectors s ON sub.sector_id = s.id
        INNER JOIN managers m ON p.manager_code = m.code
        LEFT JOIN plant_taxonomy tx ON p.taxonomy_id = tx.id
        LEFT JOIN ai_taxonomy_tasks ai ON p.uid = ai.plant_uid
        {where_clause}
        ORDER BY p.created_at DESC, p.plant_code ASC
    """
    return [dict(r) for r in db.execute(query, params).fetchall()]


def get_plant_by_uid(db: sqlite3.Connection, uid: str) -> Optional[Dict[str, Any]]:
    query = """
        SELECT
            p.uid,
            p.plant_code,
            p.subsector_seq,
            p.name,
            p.quantity,
            p.needs_individual_split,
            p.status,
            p.photo_filename,
            p.description,
            p.characteristics,
            p.ecological_benefits,
            p.notes,
            p.created_at,
            p.taxonomy_id,
            pt.code AS plant_type_code,
            pt.name AS plant_type_name,
            tx.kingdom,
            tx.division,
            tx.class_name,
            tx.order_name,
            tx.family,
            tx.genus,
            tx.species,
            tx.scientific_name,
            tx.verification_status AS taxonomy_verification_status,
            s.code AS sector_code,
            s.name AS sector_name,
            sub.code AS subsector_code,
            sub.name AS subsector_name,
            m.code AS manager_code,
            m.name AS manager_name,
            ai.status AS ai_task_status,
            ai.attempt_count AS ai_attempt_count,
            ai.max_attempts AS ai_max_attempts,
            ai.last_error AS ai_last_error
        FROM plants p
        INNER JOIN plant_types pt ON p.plant_type_id = pt.id
        INNER JOIN subsectors sub ON p.subsector_id = sub.id
        INNER JOIN sectors s ON sub.sector_id = s.id
        INNER JOIN managers m ON p.manager_code = m.code
        LEFT JOIN plant_taxonomy tx ON p.taxonomy_id = tx.id
        LEFT JOIN ai_taxonomy_tasks ai ON p.uid = ai.plant_uid
        WHERE p.uid = ?
    """
    row = db.execute(query, (uid,)).fetchone()
    return dict(row) if row else None


def get_form_cascading_metadata(db: sqlite3.Connection) -> Dict[str, Any]:
    sectors = [
        dict(r) for r in db.execute("SELECT id, code, name FROM sectors ORDER BY name ASC")
    ]
    subsectors = [
        dict(r)
        for r in db.execute(
            """
            SELECT
                sub.id,
                sub.sector_id,
                sub.code,
                sub.name,
                COALESCE(MAX(p.subsector_seq), 0) + 1 AS next_seq
            FROM subsectors sub
            LEFT JOIN plants p ON sub.id = p.subsector_id
            GROUP BY sub.id, sub.sector_id, sub.code, sub.name
            ORDER BY sub.name ASC
            """
        )
    ]
    plant_types = [
        dict(r) for r in db.execute("SELECT id, code, name FROM plant_types ORDER BY name ASC")
    ]
    plant_managers = [
        dict(r)
        for r in db.execute(
            "SELECT code, name FROM managers WHERE is_plant_manager = 1 ORDER BY code ASC"
        )
    ]
    sector_managers = [
        dict(r)
        for r in db.execute(
            """
            SELECT sm.sector_id, sm.manager_code, m.name AS manager_name
            FROM sector_managers sm
            INNER JOIN managers m ON sm.manager_code = m.code
            WHERE m.is_plant_manager = 1
            ORDER BY sm.manager_code ASC
            """
        )
    ]
    taxonomies = [
        dict(r)
        for r in db.execute(
            """
            SELECT id, kingdom, division, class_name, order_name, family, genus, species, scientific_name, verification_status
            FROM plant_taxonomy
            ORDER BY family ASC, genus ASC, scientific_name ASC
            """
        )
    ]
    known_plants = [
        dict(r)
        for r in db.execute(
            """
            SELECT DISTINCT
                p.name,
                p.plant_type_id,
                tx.kingdom,
                tx.division,
                tx.class_name,
                tx.order_name,
                tx.family,
                tx.genus,
                tx.species,
                tx.scientific_name
            FROM plants p
            LEFT JOIN plant_taxonomy tx ON p.taxonomy_id = tx.id
            ORDER BY p.name ASC
            """
        )
    ]

    return {
        "sectors": sectors,
        "subsectors": subsectors,
        "plant_types": plant_types,
        "plant_managers": plant_managers,
        "sector_managers": sector_managers,
        "taxonomies": taxonomies,
        "known_plants": known_plants,
    }


def update_plant_entry(
    db: sqlite3.Connection,
    uid: str,
    status: str,
    plant_type_id: int,
    subsector_id: int,
    notes: Optional[str] = None,
) -> None:
    with db:
        current = db.execute(
            """
            SELECT p.subsector_id, p.subsector_seq, p.plant_type_id, p.manager_code
            FROM plants p
            WHERE p.uid = ?
            """,
            (uid,),
        ).fetchone()
        if not current:
            raise ValueError("Data tanaman tidak ditemukan.")

        type_row = db.execute(
            "SELECT code FROM plant_types WHERE id = ?",
            (plant_type_id,),
        ).fetchone()
        if not type_row:
            raise ValueError("Jenis tanaman baru tidak valid.")

        loc_row = db.execute(
            """
            SELECT s.code AS sector_code, sub.code AS subsector_code
            FROM subsectors sub
            INNER JOIN sectors s ON sub.sector_id = s.id
            WHERE sub.id = ?
            """,
            (subsector_id,),
        ).fetchone()
        if not loc_row:
            raise ValueError("Subsektor baru tidak valid.")

        subsector_changed = int(current["subsector_id"]) != int(subsector_id)
        type_changed = int(current["plant_type_id"]) != int(plant_type_id)

        if subsector_changed or type_changed:
            new_seq = (
                get_next_subsector_sequence(db, subsector_id)
                if subsector_changed
                else int(current["subsector_seq"])
            )
            new_plant_code = build_public_plant_id(
                sector_code=loc_row["sector_code"],
                subsector_code=loc_row["subsector_code"],
                subsector_seq=new_seq,
                plant_type_code=type_row["code"],
                manager_code=current["manager_code"],
            )
            db.execute(
                """
                UPDATE plants
                SET status = ?,
                    plant_type_id = ?,
                    subsector_id = ?,
                    subsector_seq = ?,
                    plant_code = ?,
                    notes = ?,
                    updated_at = datetime('now', 'localtime')
                WHERE uid = ?
                """,
                (
                    status.strip(),
                    plant_type_id,
                    subsector_id,
                    new_seq,
                    new_plant_code,
                    (notes or "").strip() or None,
                    uid,
                ),
            )
        else:
            db.execute(
                """
                UPDATE plants
                SET status = ?,
                    notes = ?,
                    updated_at = datetime('now', 'localtime')
                WHERE uid = ?
                """,
                (status.strip(), (notes or "").strip() or None, uid),
            )


def update_plant_with_references(
    db: sqlite3.Connection,
    uid: str,
    status: str,
    plant_type_name: str,
    plant_type_code: str,
    sector_name: str,
    sector_code: str,
    subsector_name: str,
    subsector_code: str,
    notes: Optional[str] = None,
    description: Optional[str] = None,
    characteristics: Optional[str] = None,
    ecological_benefits: Optional[str] = None,
) -> None:
    """Memperbarui referensi jenis/lokasi, informasi ensiklopedia, dan data tanaman secara atomik."""
    with db:
        plant_type_id = get_or_create_plant_type(db, plant_type_name, plant_type_code)
        sector_id = get_or_create_sector(db, sector_name, sector_code)
        subsector_id = get_or_create_subsector(db, sector_id, subsector_name, subsector_code)

        current = db.execute(
            """
            SELECT p.subsector_id, p.subsector_seq, p.plant_type_id, p.manager_code
            FROM plants p
            WHERE p.uid = ?
            """,
            (uid,),
        ).fetchone()
        if not current:
            raise ValueError("Data tanaman tidak ditemukan.")

        type_row = db.execute("SELECT code FROM plant_types WHERE id = ?", (plant_type_id,)).fetchone()
        loc_row = db.execute(
            """
            SELECT s.code AS sector_code, sub.code AS subsector_code
            FROM subsectors sub
            INNER JOIN sectors s ON sub.sector_id = s.id
            WHERE sub.id = ?
            """,
            (subsector_id,),
        ).fetchone()

        subsector_changed = int(current["subsector_id"]) != int(subsector_id)
        type_changed = int(current["plant_type_id"]) != int(plant_type_id)

        desc_val = (description or "").strip() or None
        char_val = (characteristics or "").strip() or None
        eco_val = (ecological_benefits or "").strip() or None
        notes_val = (notes or "").strip() or None

        if subsector_changed or type_changed:
            new_seq = (
                get_next_subsector_sequence(db, subsector_id)
                if subsector_changed
                else int(current["subsector_seq"])
            )
            new_plant_code = build_public_plant_id(
                sector_code=loc_row["sector_code"],
                subsector_code=loc_row["subsector_code"],
                subsector_seq=new_seq,
                plant_type_code=type_row["code"],
                manager_code=current["manager_code"],
            )
            db.execute(
                """
                UPDATE plants
                SET status = ?,
                    plant_type_id = ?,
                    subsector_id = ?,
                    subsector_seq = ?,
                    plant_code = ?,
                    description = ?,
                    characteristics = ?,
                    ecological_benefits = ?,
                    notes = ?,
                    updated_at = datetime('now', 'localtime')
                WHERE uid = ?
                """,
                (
                    status.strip(),
                    plant_type_id,
                    subsector_id,
                    new_seq,
                    new_plant_code,
                    desc_val,
                    char_val,
                    eco_val,
                    notes_val,
                    uid,
                ),
            )
        else:
            db.execute(
                """
                UPDATE plants
                SET status = ?,
                    description = ?,
                    characteristics = ?,
                    ecological_benefits = ?,
                    notes = ?,
                    updated_at = datetime('now', 'localtime')
                WHERE uid = ?
                """,
                (status.strip(), desc_val, char_val, eco_val, notes_val, uid),
            )


def delete_plant_entry(db: sqlite3.Connection, uid: str) -> Dict[str, Any]:
    with db:
        row = db.execute(
            "SELECT photo_filename, taxonomy_id FROM plants WHERE uid = ?",
            (uid,),
        ).fetchone()
        if not row:
            return {"deleted": False, "photo_filename": None, "can_delete_photo": False}

        photo_filename = row["photo_filename"]
        taxonomy_id = row["taxonomy_id"]

        db.execute("DELETE FROM plants WHERE uid = ?", (uid,))

        if taxonomy_id is not None:
            still_used_tx = db.execute(
                "SELECT 1 FROM plants WHERE taxonomy_id = ? LIMIT 1",
                (taxonomy_id,),
            ).fetchone()
            if not still_used_tx:
                db.execute(
                    "DELETE FROM plant_taxonomy WHERE id = ? AND verification_status = 'pending'",
                    (taxonomy_id,),
                )

        can_delete_photo = False
        if photo_filename:
            still_used_photo = is_photo_referenced_by_any_plant(db, photo_filename)
            can_delete_photo = not still_used_photo

    return {
        "deleted": True,
        "photo_filename": photo_filename,
        "can_delete_photo": can_delete_photo,
    }


def verify_plant_taxonomy(db: sqlite3.Connection, uid: str, action: str) -> None:
    if action not in ("verified", "rejected"):
        raise ValueError("Status verifikasi tidak valid.")

    with db:
        row = db.execute("SELECT taxonomy_id FROM plants WHERE uid = ?", (uid,)).fetchone()
        if not row or row["taxonomy_id"] is None:
            raise ValueError("Tanaman belum memiliki data taksonomi.")

        tx_id = int(row["taxonomy_id"])
        shared_count = db.execute(
            "SELECT COUNT(*) AS cnt FROM plants WHERE taxonomy_id = ?",
            (tx_id,),
        ).fetchone()["cnt"]

        if action == "rejected" and shared_count > 1:
            db.execute("UPDATE plants SET taxonomy_id = NULL WHERE uid = ?", (uid,))
        else:
            db.execute(
                "UPDATE plant_taxonomy SET verification_status = ? WHERE id = ?",
                (action, tx_id),
            )


def get_adiwiyata_impact_stats(db: sqlite3.Connection) -> Dict[str, int]:
    """
    Mengambil statistik dampak lingkungan secara aktual menggunakan COUNT(*)
    (1 baris = 1 individu tanaman).
    """
    plant_row = db.execute("SELECT COUNT(*) AS total_plants FROM plants").fetchone()
    sector_row = db.execute(
        """
        SELECT COUNT(DISTINCT s.id) AS total_sectors
        FROM sectors s
        INNER JOIN subsectors sub ON sub.sector_id = s.id
        INNER JOIN plants p ON p.subsector_id = sub.id
        """
    ).fetchone()
    type_row = db.execute(
        """
        SELECT COUNT(DISTINCT pt.id) AS total_types
        FROM plant_types pt
        INNER JOIN plants p ON p.plant_type_id = pt.id
        """
    ).fetchone()

    total_plants = int(plant_row["total_plants"]) if plant_row else 0
    total_sectors = int(sector_row["total_sectors"]) if sector_row else 0
    total_categories = int(type_row["total_types"]) if type_row else 0

    return {
        "total_records": total_plants,
        "total_individuals": total_plants,
        "total_sectors": total_sectors,
        "total_categories": total_categories,
    }