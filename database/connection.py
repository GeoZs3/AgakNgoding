import sqlite3
from pathlib import Path
from flask import current_app, g


def get_db() -> sqlite3.Connection:
    """Mengambil atau membuat koneksi SQLite aktif dengan PRAGMA foreign_keys = ON."""
    if "db" not in g:
        db_path: Path = current_app.config["DATABASE_PATH"]
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        g.db = conn
    return g.db


def close_db(exception=None) -> None:
    """Menutup koneksi database saat request selesai."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app) -> None:
    """
    Membuat folder instance, upload folder, file database SQLite, dan seluruh tabel
    secara idempoten tanpa mengisi data dummy.
    """
    db_path: Path = app.config["DATABASE_PATH"]
    schema_path: Path = app.config["SCHEMA_PATH"]
    upload_dir: Path = app.config["UPLOAD_FOLDER"]

    db_path.parent.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        with open(schema_path, "r", encoding="utf-8") as schema_file:
            conn.executescript(schema_file.read())
        conn.commit()