PRAGMA foreign_keys = ON;

-- 1. Tabel Penanggung Jawab (9 P, dengan 5 P khusus pengurus tanaman)
CREATE TABLE IF NOT EXISTS managers (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    is_plant_manager INTEGER NOT NULL DEFAULT 0 CHECK (is_plant_manager IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 2. Tabel Akun Pengguna (Guru dan P Pengurus Tanaman)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('guru', 'p_manager')),
    manager_code TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    CONSTRAINT fk_user_manager
        FOREIGN KEY (manager_code)
        REFERENCES managers (code)
        ON UPDATE CASCADE
        ON DELETE SET NULL
);

-- 3. Tabel Kamus Sektor (Wilayah Utama Sekolah)
CREATE TABLE IF NOT EXISTS sectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 4. Tabel Pemetaan Sektor <-> P Pengurus Tanaman
CREATE TABLE IF NOT EXISTS sector_managers (
    sector_id INTEGER NOT NULL,
    manager_code TEXT NOT NULL,
    PRIMARY KEY (sector_id, manager_code),
    CONSTRAINT fk_sm_sector
        FOREIGN KEY (sector_id)
        REFERENCES sectors (id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    CONSTRAINT fk_sm_manager
        FOREIGN KEY (manager_code)
        REFERENCES managers (code)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

-- 5. Tabel Kamus Subsektor (Titik Lokasi Spesifik di dalam Sektor)
CREATE TABLE IF NOT EXISTS subsectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sector_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    CONSTRAINT fk_subsector_sector
        FOREIGN KEY (sector_id)
        REFERENCES sectors (id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    CONSTRAINT uq_sector_subsector_code
        UNIQUE (sector_id, code),
    CONSTRAINT uq_sector_subsector_name
        UNIQUE (sector_id, name)
);

-- 6. Tabel Jenis Tanaman (Klasifikasi Fungsional)
CREATE TABLE IF NOT EXISTS plant_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 7. Tabel Taksonomi Biologis (Dengan Status Verifikasi)
CREATE TABLE IF NOT EXISTS plant_taxonomy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kingdom TEXT DEFAULT 'Plantae',
    division TEXT,
    class_name TEXT,
    order_name TEXT,
    family TEXT,
    genus TEXT,
    species TEXT,
    scientific_name TEXT,
    verification_status TEXT NOT NULL DEFAULT 'verified'
        CHECK (verification_status IN ('pending', 'verified', 'rejected')),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 8. Tabel Utama Inventaris Tanaman
CREATE TABLE IF NOT EXISTS plants (
    uid TEXT PRIMARY KEY CHECK (length(uid) = 36),
    plant_code TEXT NOT NULL UNIQUE,
    subsector_seq INTEGER NOT NULL CHECK (subsector_seq >= 1),
    name TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 0),
    needs_individual_split INTEGER NOT NULL DEFAULT 0 CHECK (needs_individual_split IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'Hidup',
    plant_type_id INTEGER NOT NULL,
    taxonomy_id INTEGER,
    subsector_id INTEGER NOT NULL,
    manager_code TEXT NOT NULL,
    photo_filename TEXT,
    description TEXT,
    characteristics TEXT,
    ecological_benefits TEXT,
    notes TEXT,
    created_by_user_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    CONSTRAINT fk_plant_type
        FOREIGN KEY (plant_type_id)
        REFERENCES plant_types (id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    CONSTRAINT fk_plant_taxonomy
        FOREIGN KEY (taxonomy_id)
        REFERENCES plant_taxonomy (id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    CONSTRAINT fk_plant_subsector
        FOREIGN KEY (subsector_id)
        REFERENCES subsectors (id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    CONSTRAINT fk_plant_manager
        FOREIGN KEY (manager_code)
        REFERENCES managers (code)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    CONSTRAINT fk_plant_creator
        FOREIGN KEY (created_by_user_id)
        REFERENCES users (id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    CONSTRAINT uq_subsector_sequence
        UNIQUE (subsector_id, subsector_seq)
);

-- 9. Tabel Status Proses Taksonomi AI Persisten
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

-- Indexes untuk optimasi pencarian, filter, dan antrean AI
CREATE INDEX IF NOT EXISTS idx_subsectors_sector_id ON subsectors (sector_id);
CREATE INDEX IF NOT EXISTS idx_plants_plant_code ON plants (plant_code);
CREATE INDEX IF NOT EXISTS idx_plants_name ON plants (name);
CREATE INDEX IF NOT EXISTS idx_plants_status ON plants (status);
CREATE INDEX IF NOT EXISTS idx_plants_type_id ON plants (plant_type_id);
CREATE INDEX IF NOT EXISTS idx_plants_subsector_id ON plants (subsector_id);
CREATE INDEX IF NOT EXISTS idx_plants_taxonomy_id ON plants (taxonomy_id);
CREATE INDEX IF NOT EXISTS idx_taxonomy_family ON plant_taxonomy (family);
CREATE INDEX IF NOT EXISTS idx_taxonomy_genus ON plant_taxonomy (genus);
CREATE INDEX IF NOT EXISTS idx_taxonomy_verification_status ON plant_taxonomy (verification_status);
CREATE INDEX IF NOT EXISTS idx_ai_tasks_status ON ai_taxonomy_tasks (status);