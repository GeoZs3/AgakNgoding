import json
import os
import sqlite3
import threading
from typing import Any, Dict, List
from openai import OpenAI
from google import genai
from google.genai import types
from pathlib import Path


def _save_taxonomy_to_plant(db: sqlite3.Connection, plant_uid: str, taxonomy_data: Dict[str, str]) -> None:
    """Menyimpan atau menautkan hasil taksonomi AI ke entri tanaman berdasarkan UID."""
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

    with db:
        taxonomy_id = None
        if scientific_name:
            existing = db.execute(
                "SELECT id FROM plant_taxonomy WHERE scientific_name = ?",
                (scientific_name,),
            ).fetchone()
            if existing:
                taxonomy_id = existing["id"]
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
            cur = db.execute(
                """
                INSERT INTO plant_taxonomy
                    (kingdom, division, class_name, order_name, family, genus, species, scientific_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (kingdom, division, class_name, order_name, family, genus, species, scientific_name),
            )
            taxonomy_id = cur.lastrowid

        db.execute(
            "UPDATE plants SET taxonomy_id = ?, updated_at = datetime('now', 'localtime') WHERE uid = ?",
            (taxonomy_id, plant_uid),
        )


def attach_taxonomy_in_background(
    db_path: Path,
    plant_uid: str,
    plant_name: str,
    gemini_api_key: str,
    gemini_model: str,
    openai_api_key: str,
    openai_model: str,
) -> None:
    """Menjalankan identifikasi taksonomi AI di thread latar belakang tanpa memblokir request HTTP."""

    def _worker():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            res = lookup_taxonomy_with_ai(
                db=conn,
                plant_name=plant_name,
                gemini_api_key=gemini_api_key,
                gemini_model=gemini_model,
                openai_api_key=openai_api_key,
                openai_model=openai_model,
            )
            if res.get("found") and res.get("taxonomy"):
                _save_taxonomy_to_plant(conn, plant_uid, res["taxonomy"])
        except Exception as exc:
            print(f"[Background AI Taxonomy] Gagal memproses '{plant_name}' ({plant_uid}): {exc}")
        finally:
            conn.close()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

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
    Mencari taksonomi biologis dari database lokal terlebih dahulu, lalu menggunakan
    layanan AI yang aktif (Gemini / OpenAI) dengan automatic fallback jika salah satu gagal.
    """
    clean_name = plant_name.strip()
    if not clean_name:
        return {"found": False, "source": "empty", "taxonomy": {}}

    # 1. Cek cache database lokal terlebih dahulu
    local_row = db.execute(
        """
        SELECT
            tx.kingdom, tx.division, tx.class_name, tx.order_name,
            tx.family, tx.genus, tx.species, tx.scientific_name
        FROM plants p
        INNER JOIN plant_taxonomy tx ON p.taxonomy_id = tx.id
        WHERE LOWER(p.name) = LOWER(?)
        LIMIT 1
        """,
        (clean_name,),
    ).fetchone()

    if local_row:
        return {
            "found": True,
            "source": "database",
            "taxonomy": dict(local_row),
        }

    # 2. Kumpulkan daftar provider AI yang memiliki API Key aktif
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
            "message": "Tidak ada API Key aktif (GEMINI_API_KEY maupun OPENAI_API_KEY kosong di .env).",
            "taxonomy": {},
        }

    errors: List[str] = []
    for provider_name, runner in providers:
        try:
            return runner()
        except Exception as exc:
            errors.append(f"{provider_name}: {exc}")

    return {
        "found": False,
        "source": "error",
        "message": f"Semua layanan AI gagal merespons ({' | '.join(errors)})",
        "taxonomy": {},
    }