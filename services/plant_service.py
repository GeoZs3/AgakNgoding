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
    """Mencari sektor berdasarkan nama (case-insensitive); jika belum ada, buat entri baru."""
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
    """Mencari subsektor dalam sektor terkait; jika belum ada, buat entri baru."""
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
    """Mencari jenis tanaman berdasarkan nama; jika belum ada, buat entri baru."""
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
    """Menghitung nomor urut tanaman berikutnya (IDSUBSEKTOR) di dalam suatu subsektor."""
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
    """
    Menyusun ID publik tanaman sesuai format:
    SEKTOR-SUB-IDSUBSEKTOR-TIPETANAMAN-P
    Contoh: GB-TS-001-HIAS-P1
    """
    seq_formatted = f"{subsector_seq:03d}"
    return (
        f"{sector_code.upper()}-"
        f"{subsector_code.upper()}-"
        f"{seq_formatted}-"
        f"{plant_type_code.upper()}-"
        f"{manager_code.upper()}"
    )


def get_filter_tag_groups(db: sqlite3.Connection) -> Dict[str, List[Dict[str, str]]]:
    """
    Mengambil daftar tags terstruktur dari atribut database untuk filter 3-state (Include/Exclude):
    1. Status Hidup
    2. Lokasi Tanaman (Sektor)
    3. Jenis Tanaman
    4. Taksonomi (Famili & Genus)
    """
    groups: Dict[str, List[Dict[str, str]]] = {
        "Status Hidup": [],
        "Lokasi (Sektor)": [],
        "Jenis Tanaman": [],
        "Taksonomi (Famili)": [],
        "Taksonomi (Genus)": [],
    }

    # 1. Status Hidup
    status_set = {"Hidup", "Perawatan Khusus", "Layu", "Mati"}
    for r in db.execute("SELECT DISTINCT status FROM plants WHERE status IS NOT NULL AND status != ''"):
        status_set.add(r["status"])
    for st in sorted(status_set):
        groups["Status Hidup"].append({"key": f"status:{st}", "label": st})

    # 2. Lokasi (Sektor)
    for r in db.execute("SELECT code, name FROM sectors ORDER BY name ASC"):
        groups["Lokasi (Sektor)"].append({
            "key": f"sector:{r['code']}",
            "label": f"{r['name']} ({r['code']})",
        })

    # 3. Jenis Tanaman
    for r in db.execute("SELECT code, name FROM plant_types ORDER BY name ASC"):
        groups["Jenis Tanaman"].append({
            "key": f"type:{r['code']}",
            "label": f"{r['name']} ({r['code']})",
        })

    # 4. Taksonomi - Famili
    for r in db.execute(
        "SELECT DISTINCT family FROM plant_taxonomy WHERE family IS NOT NULL AND family != '' ORDER BY family ASC"
    ):
        groups["Taksonomi (Famili)"].append({
            "key": f"family:{r['family']}",
            "label": r["family"],
        })

    # 5. Taksonomi - Genus
    for r in db.execute(
        "SELECT DISTINCT genus FROM plant_taxonomy WHERE genus IS NOT NULL AND genus != '' ORDER BY genus ASC"
    ):
        groups["Taksonomi (Genus)"].append({
            "key": f"genus:{r['genus']}",
            "label": r["genus"],
        })

    return groups


def _build_tag_condition(tag_key: str, is_include: bool, params: List[Any]) -> Optional[str]:
    """Menerjemahkan key tag ('kategori:nilai') menjadi klausa SQL berparameter."""
    if ":" not in tag_key:
        return None
    category, value = tag_key.split(":", 1)
    value = value.strip()
    if not value:
        return None

    if category == "status":
        params.append(value)
        return "p.status = ?" if is_include else "(p.status IS NULL OR p.status != ?)"

    if category == "sector":
        params.append(value)
        return "s.code = ?" if is_include else "(s.code IS NULL OR s.code != ?)"

    if category == "type":
        params.append(value)
        return "pt.code = ?" if is_include else "(pt.code IS NULL OR pt.code != ?)"

    if category == "family":
        params.append(value)
        return "tx.family = ?" if is_include else "(tx.family IS NULL OR tx.family != ?)"

    if category == "genus":
        params.append(value)
        return "tx.genus = ?" if is_include else "(tx.genus IS NULL OR tx.genus != ?)"

    return None


def get_plants_grouped_by_type(
    db: sqlite3.Connection,
    search_query: str = "",
    include_tags: Optional[List[str]] = None,
    exclude_tags: Optional[List[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Mengambil data tanaman yang dikelompokkan per jenis tanaman (rak buku),
    dengan pencarian nama dan filter 3-state (include & exclude tags).
    """
    include_tags = include_tags or []
    exclude_tags = exclude_tags or []
    search_query = search_query.strip()

    conditions: List[str] = []
    params: List[Any] = []

    if search_query:
        conditions.append("(p.name LIKE ? OR tx.scientific_name LIKE ? OR p.plant_code LIKE ?)")
        like_val = f"%{search_query}%"
        params.extend([like_val, like_val, like_val])

    inc_by_cat: Dict[str, List[str]] = defaultdict(list)
    for t in include_tags:
        if ":" in t:
            cat = t.split(":", 1)[0]
            inc_by_cat[cat].append(t)

    for cat, keys in inc_by_cat.items():
        or_clauses: List[str] = []
        for k in keys:
            clause = _build_tag_condition(k, is_include=True, params=params)
            if clause:
                or_clauses.append(clause)
        if or_clauses:
            conditions.append(f"({' OR '.join(or_clauses)})")

    for k in exclude_tags:
        clause = _build_tag_condition(k, is_include=False, params=params)
        if clause:
            conditions.append(clause)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT
            p.uid,
            p.plant_code,
            p.name,
            p.quantity,
            p.status,
            p.photo_filename,
            pt.name AS plant_type_name,
            tx.scientific_name,
            s.name AS sector_name,
            sub.name AS subsector_name
        FROM plants p
        INNER JOIN plant_types pt ON p.plant_type_id = pt.id
        INNER JOIN subsectors sub ON p.subsector_id = sub.id
        INNER JOIN sectors s ON sub.sector_id = s.id
        LEFT JOIN plant_taxonomy tx ON p.taxonomy_id = tx.id
        {where_clause}
        ORDER BY pt.name ASC, p.name ASC
    """
    rows = db.execute(query, params).fetchall()
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        item = dict(row)
        grouped[item["plant_type_name"]].append(item)

    return dict(grouped)


def get_plant_by_uid(db: sqlite3.Connection, uid: str) -> Optional[Dict[str, Any]]:
    """Mengambil detail lengkap satu entri tanaman berdasarkan UID internal."""
    query = """
        SELECT
            p.uid,
            p.plant_code,
            p.subsector_seq,
            p.name,
            p.quantity,
            p.status,
            p.photo_filename,
            p.notes,
            p.created_at,
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
            s.code AS sector_code,
            s.name AS sector_name,
            sub.code AS subsector_code,
            sub.name AS subsector_name,
            m.code AS manager_code,
            m.name AS manager_name
        FROM plants p
        INNER JOIN plant_types pt ON p.plant_type_id = pt.id
        INNER JOIN subsectors sub ON p.subsector_id = sub.id
        INNER JOIN sectors s ON sub.sector_id = s.id
        INNER JOIN managers m ON p.manager_code = m.code
        LEFT JOIN plant_taxonomy tx ON p.taxonomy_id = tx.id
        WHERE p.uid = ?
    """
    row = db.execute(query, (uid,)).fetchone()
    return dict(row) if row else None


def get_form_cascading_metadata(db: sqlite3.Connection) -> Dict[str, Any]:
    """
    Mengambil seluruh dictionary lokasi, P pengurus tanaman, jenis tanaman,
    dan kamus taksonomi untuk mendukung searchable combobox & autofill di frontend.
    """
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
            SELECT id, kingdom, division, class_name, order_name, family, genus, species, scientific_name
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
    created_by_user_id: Optional[int] = None,
) -> Dict[str, str]:
    """
    Menyimpan entri tanaman baru secara transaksional, membuat/menghubungkan taksonomi,
    menghitung nomor urut subsektor, dan membentuk ID publik SEKTOR-SUB-IDSUBSEKTOR-TIPETANAMAN-P.
    """
    with db:
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
            if scientific_name:
                existing_tx = db.execute(
                    "SELECT id FROM plant_taxonomy WHERE scientific_name = ?",
                    (scientific_name,),
                ).fetchone()
                if existing_tx:
                    taxonomy_id = existing_tx["id"]
                    db.execute(
                        """
                        UPDATE plant_taxonomy
                        SET kingdom = COALESCE(?, kingdom),
                            division = COALESCE(?, division),
                            class_name = COALESCE(?, class_name),
                            order_name = COALESCE(?, order_name),
                            family = COALESCE(?, family),
                            genus = COALESCE(?, genus),
                            species = COALESCE(?, species)
                        WHERE id = ?
                        """,
                        (kingdom, division, class_name, order_name, family, genus, species, taxonomy_id),
                    )
            if taxonomy_id is None:
                cur_tx = db.execute(
                    """
                    INSERT INTO plant_taxonomy
                        (kingdom, division, class_name, order_name, family, genus, species, scientific_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (kingdom, division, class_name, order_name, family, genus, species, scientific_name),
                )
                taxonomy_id = cur_tx.lastrowid

        uid = generate_plant_uid()
        subsector_seq = get_next_subsector_sequence(db, subsector_id)
        plant_code = build_public_plant_id(
            sector_code=loc_row["sector_code"],
            subsector_code=loc_row["subsector_code"],
            subsector_seq=subsector_seq,
            plant_type_code=type_row["code"],
            manager_code=mgr_row["code"],
        )

        db.execute(
            """
            INSERT INTO plants (
                uid, plant_code, subsector_seq, name, quantity, status,
                plant_type_id, taxonomy_id, subsector_id, manager_code,
                photo_filename, notes, created_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uid,
                plant_code,
                subsector_seq,
                name.strip(),
                quantity,
                status.strip(),
                plant_type_id,
                taxonomy_id,
                subsector_id,
                mgr_row["code"],
                photo_filename,
                (notes or "").strip() or None,
                created_by_user_id,
            ),
        )

    return {"uid": uid, "plant_code": plant_code}

def update_plant_entry(
    db: sqlite3.Connection,
    uid: str,
    status: str,
    plant_type_id: int,
    subsector_id: int,
    notes: Optional[str] = None,
) -> None:
    """
    Memperbarui status tanaman, jenis tanaman, lokasi (subsektor), dan catatan.
    Jika subsektor atau jenis tanaman berubah, plant_code ikut diperbarui otomatis.
    """
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


def delete_plant_entry(db: sqlite3.Connection, uid: str) -> Optional[str]:
    """Menghapus entri tanaman dari database dan mengembalikan nama file fotonya untuk dihapus."""
    with db:
        row = db.execute("SELECT photo_filename FROM plants WHERE uid = ?", (uid,)).fetchone()
        if not row:
            return None
        db.execute("DELETE FROM plants WHERE uid = ?", (uid,))
        return row["photo_filename"]