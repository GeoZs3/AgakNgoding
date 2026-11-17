import sqlite3
from pathlib import Path
from flask import current_app, g


def get_db() -> sqlite3.Connection:
    """Membuka atau mengembalikan koneksi SQLite per-request."""
    if "db" not in g:
        db_path = Path(current_app.config["DATABASE_PATH"])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 10000;")
        g.db = conn
    return g.db


def close_db(e=None) -> None:
    """Menutup koneksi SQLite di akhir request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def run_safe_migrations(conn: sqlite3.Connection) -> None:
    """
    Migrasi non-destruktif untuk database SQLite yang sudah ada maupun database baru:
    - Menambahkan verification_status pada plant_taxonomy jika belum ada.
    - Menambahkan kolom ensiklopedia & penanda migrasi individual pada plants jika belum ada.
    - Memastikan tabel ai_taxonomy_tasks tersedia.
    """
    tx_cols = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(plant_taxonomy)").fetchall()
    }
    if tx_cols:
        if "verification_status" not in tx_cols:
            conn.execute(
                """
                ALTER TABLE plant_taxonomy
                ADD COLUMN verification_status TEXT NOT NULL DEFAULT 'verified'
                """
            )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_taxonomy_verification_status
                ON plant_taxonomy (verification_status)
            """
        )

    plant_cols = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(plants)").fetchall()
    }
    if plant_cols:
        alter_statements = []
        if "description" not in plant_cols:
            alter_statements.append("ALTER TABLE plants ADD COLUMN description TEXT")
        if "characteristics" not in plant_cols:
            alter_statements.append("ALTER TABLE plants ADD COLUMN characteristics TEXT")
        if "ecological_benefits" not in plant_cols:
            alter_statements.append("ALTER TABLE plants ADD COLUMN ecological_benefits TEXT")
        if "needs_individual_split" not in plant_cols:
            alter_statements.append(
                "ALTER TABLE plants ADD COLUMN needs_individual_split INTEGER NOT NULL DEFAULT 0"
            )
        for stmt in alter_statements:
            conn.execute(stmt)

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ai_taxonomy_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_uid TEXT NOT NULL UNIQUE,
                plant_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                last_error TEXT,
                locked_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                CONSTRAINT fk_ai_task_plant
                    FOREIGN KEY (plant_uid)
                    REFERENCES plants (uid)
                    ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_ai_tasks_status
                ON ai_taxonomy_tasks (status);
            """
        )


def init_db(app) -> None:
    """Inisialisasi skema & migrasi aman saat aplikasi dimulai."""
    db_path = Path(app.config["DATABASE_PATH"])
    schema_path = Path(app.config["SCHEMA_PATH"])
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        with conn:
            run_safe_migrations(conn)
            if schema_path.exists():
                conn.executescript(schema_path.read_text(encoding="utf-8"))
    finally:
        conn.close()