import json
import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from openai import OpenAI
from google import genai
from google.genai import types


TAXONOMY_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "is_valid_plant": {"type": "boolean"},
        "kingdom": {"type": "string"},
        "division": {"type": "string"},
        "class_name": {"type": "string"},
        "order_name": {"type": "string"},
        "family": {"type": "string"},
        "genus": {"type": "string"},
        "species": {"type": "string"},
        "scientific_name": {"type": "string"},
    },
    "required": [
        "is_valid_plant",
        "kingdom",
        "division",
        "class_name",
        "order_name",
        "family",
        "genus",
        "species",
        "scientific_name",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "Anda adalah ahli botani dan taksonomi tumbuhan untuk inventaris sekolah Adiwiyata di Indonesia. "
    "Diberikan nama umum tanaman (bahasa Indonesia atau daerah), kembalikan klasifikasi taksonomi "
    "biologis paling akurat dalam tata nama binomial standar. "
    "Jika nama bukan tanaman yang dikenali, isi is_valid_plant = false dan string kosong pada field lain."
)


def sanitize_error_message(raw_error: str) -> str:
    """Menghapus potensi API key atau path sensitif sebelum menyimpan pesan error ke database."""
    cleaned = re.sub(r"(sk-[A-Za-z0-9\-_]+|AIza[A-Za-z0-9\-_]+)", "[REDACTED_KEY]", str(raw_error))
    return cleaned[:400]


def _normalize_ai_result(parsed: Dict[str, Any], clean_name: str, provider_label: str) -> Dict[str, Any]:
    if not parsed.get("is_valid_plant"):
        return {
            "found": False,
            "source": provider_label,
            "message": f"Tanaman '{clean_name}' tidak dikenali secara spesifik oleh {provider_label}.",
            "taxonomy": {},
        }

    return {
        "found": True,
        "source": provider_label,
        "taxonomy": {
            "kingdom": parsed.get("kingdom") or "Plantae",
            "division": parsed.get("division") or "",
            "class_name": parsed.get("class_name") or "",
            "order_name": parsed.get("order_name") or "",
            "family": parsed.get("family") or "",
            "genus": parsed.get("genus") or "",
            "species": parsed.get("species") or "",
            "scientific_name": parsed.get("scientific_name") or "",
        },
    }


def _query_gemini(clean_name: str, api_key: str, model: str) -> Dict[str, Any]:
    client = genai.Client(api_key=api_key)
    gemini_schema = {k: v for k, v in TAXONOMY_JSON_SCHEMA.items() if k != "additionalProperties"}

    response = client.models.generate_content(
        model=model,
        contents=f"Identifikasi taksonomi biologis untuk tanaman: {clean_name}",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.1,
            response_mime_type="application/json",
            response_schema=gemini_schema,
        ),
    )
    parsed = json.loads(response.text or "{}")
    return _normalize_ai_result(parsed, clean_name, "Gemini")


def _query_openai(clean_name: str, api_key: str, model: str) -> Dict[str, Any]:
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        temperature=0.1,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Identifikasi taksonomi biologis untuk tanaman: {clean_name}"},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "plant_taxonomy_result",
                "strict": True,
                "schema": TAXONOMY_JSON_SCHEMA,
            },
        },
    )
    parsed = json.loads(response.choices[0].message.content or "{}")
    return _normalize_ai_result(parsed, clean_name, "OpenAI")


def lookup_taxonomy_with_ai(
    db: sqlite3.Connection,
    plant_name: str,
    gemini_api_key: str = "",
    gemini_model: str = "gemini-3.8-flash",
    openai_api_key: str = "",
    openai_model: str = "gpt-4o-mini",
) -> Dict[str, Any]:
    """
    Mencari taksonomi dari cache database yang SUDAH TERVERIFIKASI terlebih dahulu,
    lalu menggunakan provider AI yang tersedia (Gemini / OpenAI) dengan automatic fallback.
    """
    clean_name = plant_name.strip()
    if not clean_name:
        return {"found": False, "source": "empty", "taxonomy": {}}

    # 1. Hanya ambil dari kamus lokal jika status taksonominya sudah 'verified'
    local_row = db.execute(
        """
        SELECT
            tx.id AS taxonomy_id,
            tx.kingdom, tx.division, tx.class_name, tx.order_name,
            tx.family, tx.genus, tx.species, tx.scientific_name
        FROM plants p
        INNER JOIN plant_taxonomy tx ON p.taxonomy_id = tx.id
        WHERE LOWER(p.name) = LOWER(?) AND tx.verification_status = 'verified'
        LIMIT 1
        """,
        (clean_name,),
    ).fetchone()

    if local_row:
        return {
            "found": True,
            "source": "database_verified",
            "verified_taxonomy_id": int(local_row["taxonomy_id"]),
            "taxonomy": dict(local_row),
        }

    resolved_gemini = (gemini_api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
    resolved_openai = (openai_api_key or os.environ.get("OPENAI_API_KEY", "")).strip()

    providers = []
    if resolved_gemini:
        providers.append(("Gemini", lambda: _query_gemini(clean_name, resolved_gemini, gemini_model)))
    if resolved_openai:
        providers.append(("OpenAI", lambda: _query_openai(clean_name, resolved_openai, openai_model)))

    if not providers:
        return {
            "found": False,
            "source": "error",
            "message": "Tidak ada layanan AI aktif (API Key tidak tersedia).",
            "taxonomy": {},
        }

    errors: List[str] = []
    for provider_name, runner in providers:
        try:
            return runner()
        except Exception as exc:
            errors.append(f"{provider_name}: {sanitize_error_message(str(exc))}")

    return {
        "found": False,
        "source": "error",
        "message": f"Semua layanan AI gagal merespons ({' | '.join(errors)})",
        "taxonomy": {},
    }


def apply_ai_taxonomy_safely(
    db: sqlite3.Connection,
    plant_uid: str,
    taxonomy_data: Dict[str, Any],
    verified_taxonomy_id: Optional[int] = None,
) -> None:
    """
    Menyimpan hasil identifikasi AI tanpa pernah menimpa record taksonomi yang sudah 'verified'
    atau record yang sedang dipakai oleh tanaman lain.
    - Jika berasal dari cache database terverifikasi (verified_taxonomy_id), tautkan langsung ke ID tersebut.
    - Jika berasal dari prediksi AI baru, selalu buat record baru berstatus 'pending' (isolasi penuh).
    """
    with db:
        plant_row = db.execute(
            "SELECT taxonomy_id FROM plants WHERE uid = ?",
            (plant_uid,),
        ).fetchone()
        if not plant_row:
            return

        # Jangan timpa jika tanaman ini sendiri sudah terhubung ke taksonomi yang berstatus 'verified'
        current_tx_id = plant_row["taxonomy_id"]
        if current_tx_id is not None:
            cur_tx = db.execute(
                "SELECT verification_status FROM plant_taxonomy WHERE id = ?",
                (current_tx_id,),
            ).fetchone()
            if cur_tx and cur_tx["verification_status"] == "verified":
                return

        if verified_taxonomy_id is not None:
            ver_row = db.execute(
                "SELECT id FROM plant_taxonomy WHERE id = ? AND verification_status = 'verified'",
                (verified_taxonomy_id,),
            ).fetchone()
            if ver_row:
                db.execute(
                    "UPDATE plants SET taxonomy_id = ?, updated_at = datetime('now', 'localtime') WHERE uid = ?",
                    (int(ver_row["id"]), plant_uid),
                )
                return

        family = (taxonomy_data.get("family") or "").strip() or None
        genus = (taxonomy_data.get("genus") or "").strip() or None
        species = (taxonomy_data.get("species") or "").strip() or None
        scientific_name = (taxonomy_data.get("scientific_name") or "").strip() or None
        division = (taxonomy_data.get("division") or "").strip() or None
        class_name = (taxonomy_data.get("class_name") or "").strip() or None
        order_name = (taxonomy_data.get("order_name") or "").strip() or None
        kingdom = (taxonomy_data.get("kingdom") or "Plantae").strip() or "Plantae"

        if not any([family, genus, species, scientific_name, division, class_name, order_name]):
            return

        # Selalu buat record terpisah berstatus 'pending' agar tidak pernah mengubah record bersama/verified
        cur = db.execute(
            """
            INSERT INTO plant_taxonomy
                (kingdom, division, class_name, order_name, family, genus, species, scientific_name, verification_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (kingdom, division, class_name, order_name, family, genus, species, scientific_name),
        )
        new_tx_id = int(cur.lastrowid)

        db.execute(
            "UPDATE plants SET taxonomy_id = ?, updated_at = datetime('now', 'localtime') WHERE uid = ?",
            (new_tx_id, plant_uid),
        )

        # Bersihkan record pending lama milik tanaman ini sendiri jika yatim
        if current_tx_id is not None:
            still_used = db.execute(
                "SELECT 1 FROM plants WHERE taxonomy_id = ? LIMIT 1",
                (current_tx_id,),
            ).fetchone()
            if not still_used:
                db.execute(
                    "DELETE FROM plant_taxonomy WHERE id = ? AND verification_status = 'pending'",
                    (current_tx_id,),
                )


def recover_stale_ai_tasks(db: sqlite3.Connection, stale_timeout_seconds: int = 120) -> int:
    """
    Memulihkan tugas AI yang tertinggal dalam status 'processing' (misal akibat aplikasi restart)
    kembali ke status 'pending' agar dapat diproses ulang dengan aman.
    """
    with db:
        cur = db.execute(
            """
            UPDATE ai_taxonomy_tasks
            SET status = 'pending',
                locked_at = NULL,
                last_error = COALESCE(last_error, 'Dipulihkan setelah aplikasi restart.'),
                updated_at = datetime('now', 'localtime')
            WHERE status = 'processing'
              AND (
                  locked_at IS NULL
                  OR (julianday('now', 'localtime') - julianday(locked_at)) * 86400 >= ?
              )
            """,
            (stale_timeout_seconds,),
        )
        return cur.rowcount


def claim_ai_task(db: sqlite3.Connection, plant_uid: str) -> Optional[Dict[str, Any]]:
    """
    Mengunci tugas AI secara atomik (pending -> processing) agar mencegah eksekusi ganda bersamaan.
    """
    with db:
        cur = db.execute(
            """
            UPDATE ai_taxonomy_tasks
            SET status = 'processing',
                attempt_count = attempt_count + 1,
                locked_at = datetime('now', 'localtime'),
                updated_at = datetime('now', 'localtime')
            WHERE plant_uid = ?
              AND status = 'pending'
              AND attempt_count < max_attempts
            """,
            (plant_uid,),
        )
        if cur.rowcount == 0:
            return None

        row = db.execute(
            "SELECT * FROM ai_taxonomy_tasks WHERE plant_uid = ?",
            (plant_uid,),
        ).fetchone()
        return dict(row) if row else None


def request_ai_task_retry(db: sqlite3.Connection, plant_uid: str, max_attempts: int = 3) -> bool:
    """
    Mengatur ulang tugas AI yang berstatus 'failed' menjadi 'pending' untuk diproses ulang.
    Tidak akan mengganggu tugas yang sedang 'processing' atau sudah 'completed'.
    """
    with db:
        cur = db.execute(
            """
            UPDATE ai_taxonomy_tasks
            SET status = 'pending',
                attempt_count = 0,
                max_attempts = ?,
                last_error = NULL,
                locked_at = NULL,
                updated_at = datetime('now', 'localtime')
            WHERE plant_uid = ?
              AND status = 'failed'
            """,
            (max_attempts, plant_uid),
        )
        return cur.rowcount > 0


def process_single_ai_task(
    db: sqlite3.Connection,
    plant_uid: str,
    gemini_api_key: str = "",
    gemini_model: str = "gemini-3.8-flash",
    openai_api_key: str = "",
    openai_model: str = "gpt-4o-mini",
) -> str:
    """
    Memproses satu tugas taksonomi AI dari database secara sinkron/deterministik.
    Mengembalikan status akhir: 'completed', 'pending' (untuk retry), 'failed', atau 'skipped'.
    """
    task = claim_ai_task(db, plant_uid)
    if not task:
        return "skipped"

    try:
        res = lookup_taxonomy_with_ai(
            db=db,
            plant_name=task["plant_name"],
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            openai_api_key=openai_api_key,
            openai_model=openai_model,
        )

        if res.get("found") and res.get("taxonomy"):
            apply_ai_taxonomy_safely(
                db=db,
                plant_uid=plant_uid,
                taxonomy_data=res["taxonomy"],
                verified_taxonomy_id=res.get("verified_taxonomy_id"),
            )
            with db:
                db.execute(
                    """
                    UPDATE ai_taxonomy_tasks
                    SET status = 'completed',
                        last_error = NULL,
                        locked_at = NULL,
                        updated_at = datetime('now', 'localtime')
                    WHERE plant_uid = ?
                    """,
                    (plant_uid,),
                )
            return "completed"

        error_msg = sanitize_error_message(res.get("message") or "Taksonomi tidak ditemukan.")
        next_status = "pending" if task["attempt_count"] < task["max_attempts"] else "failed"
        with db:
            db.execute(
                """
                UPDATE ai_taxonomy_tasks
                SET status = ?,
                    last_error = ?,
                    locked_at = NULL,
                    updated_at = datetime('now', 'localtime')
                WHERE plant_uid = ?
                """,
                (next_status, error_msg, plant_uid),
            )
        return next_status

    except Exception as exc:
        error_msg = sanitize_error_message(str(exc))
        next_status = "pending" if task["attempt_count"] < task["max_attempts"] else "failed"
        with db:
            db.execute(
                """
                UPDATE ai_taxonomy_tasks
                SET status = ?,
                    last_error = ?,
                    locked_at = NULL,
                    updated_at = datetime('now', 'localtime')
                WHERE plant_uid = ?
                """,
                (next_status, error_msg, plant_uid),
            )
        return next_status


def dispatch_ai_worker_for_pending_tasks(
    db_path: Path,
    gemini_api_key: str = "",
    gemini_model: str = "gemini-3.8-flash",
    openai_api_key: str = "",
    openai_model: str = "gpt-4o-mini",
) -> None:
    """
    Menjalankan worker latar belakang untuk memproses seluruh antrean tugas berstatus 'pending'
    di SQLite (termasuk retry otomatis hingga max_attempts).
    """
    def _worker():
        conn = sqlite3.connect(db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 10000;")
        try:
            while True:
                pending_row = conn.execute(
                    """
                    SELECT plant_uid FROM ai_taxonomy_tasks
                    WHERE status = 'pending' AND attempt_count < max_attempts
                    ORDER BY created_at ASC
                    LIMIT 1
                    """
                ).fetchone()
                if not pending_row:
                    break

                process_single_ai_task(
                    db=conn,
                    plant_uid=pending_row["plant_uid"],
                    gemini_api_key=gemini_api_key,
                    gemini_model=gemini_model,
                    openai_api_key=openai_api_key,
                    openai_model=openai_model,
                )
        finally:
            conn.close()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()