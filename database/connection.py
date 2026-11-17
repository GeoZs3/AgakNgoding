import sqlite3
from contextlib import closing
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

    with closing(sqlite3.connect(db_path)) as conn:
        with conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            with open(schema_path, "r", encoding="utf-8") as schema_file:
                conn.executescript(schema_file.read())

            user_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()
            }
            migrations = {
                "is_admin": "INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1))",
                "is_superadmin": "INTEGER NOT NULL DEFAULT 0 CHECK (is_superadmin IN (0, 1))",
                "can_edit_plants": "INTEGER NOT NULL DEFAULT 1 CHECK (can_edit_plants IN (0, 1))",
                "last_seen_at": "TEXT",
            }
            for column, definition in migrations.items():
                if column not in user_columns:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")

            conn.execute("UPDATE users SET can_edit_plants = 1 WHERE can_edit_plants != 1")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS active_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    last_seen_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                    CONSTRAINT fk_active_session_user
                        FOREIGN KEY (user_id)
                        REFERENCES users (id)
                        ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_active_sessions_user_id "
                "ON active_sessions (user_id)"
            )