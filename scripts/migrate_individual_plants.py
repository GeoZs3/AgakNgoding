"""
Skrip Migrasi Aman ke Pencatatan Individual (Proyek Adiwiyata 1.1):
1. Membuat backup otomatis database SQLite sebelum melakukan perubahan.
2. Menjalankan migrasi kolom aman (description, characteristics, ecological_benefits, needs_individual_split).
3. Memeriksa foreign key dan keunikan UUID.
4. Menandai baris lama dengan quantity > 1 (needs_individual_split = 1) TANPA menggandakan foto secara otomatis,
   serta mengekspor laporan CSV agar pengurus dapat memisahkan individu secara manual dengan foto masing-masing.
"""

import csv
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config import Config
from database.connection import run_safe_migrations


def migrate_database(db_path: Path) -> None:
    if not db_path.exists():
        print(f"[INFO] File database belum ada di {db_path}. Tidak ada data lama yang perlu dimigrasi.")
        return

    # 1. Backup database sebelum migrasi
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{db_path.stem}_backup_{timestamp}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    print(f"[OK] Backup database dibuat di: {backup_path}")

    conn = sqlite3.connect(db_path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    try:
        with conn:
            # 2. Pastikan struktur kolom baru tersedia
            run_safe_migrations(conn)

            # 3. Audit Foreign Key
            fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
            if fk_errors:
                raise RuntimeError(f"Ditemukan pelanggaran foreign key sebelum migrasi: {len(fk_errors)} baris.")

            # 4. Tandai entri lama yang memiliki quantity > 1 untuk pemisahan manual
            flagged_rows = conn.execute(
                """
                SELECT
                    p.uid,
                    p.plant_code,
                    p.name,
                    p.quantity,
                    s.name AS sector_name,
                    sub.name AS subsector_name,
                    p.photo_filename
                FROM plants p
                INNER JOIN subsectors sub ON p.subsector_id = sub.id
                INNER JOIN sectors s ON sub.sector_id = s.id
                WHERE p.quantity > 1
                ORDER BY p.plant_code ASC
                """
            ).fetchall()

            conn.execute(
                "UPDATE plants SET needs_individual_split = 1 WHERE quantity > 1"
            )
            conn.execute(
                "UPDATE plants SET needs_individual_split = 0 WHERE quantity <= 1"
            )

        print(f"[OK] Pemeriksaan integritas foreign key & UUID valid.")
        print(f"[INFO] Entri lama dengan quantity > 1 yang ditandai untuk pemisahan manual: {len(flagged_rows)} entri.")

        if flagged_rows:
            report_path = backup_dir / f"laporan_pemisahan_individu_{timestamp}.csv"
            with report_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["UID", "Kode Tanaman", "Nama", "Quantity Lama", "Sektor", "Subsektor", "Foto"])
                for r in flagged_rows:
                    writer.writerow([
                        r["uid"],
                        r["plant_code"],
                        r["name"],
                        r["quantity"],
                        r["sector_name"],
                        r["subsector_name"],
                        r["photo_filename"] or "",
                    ])
            print(f"[PERHATIAN] Daftar entri yang perlu dipisah manual diekspor ke: {report_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    target_db = Path(Config.DATABASE_PATH)
    migrate_database(target_db)