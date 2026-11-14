import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "adiwiyata-secret-key-2026")
    DATABASE_PATH = INSTANCE_DIR / "adiwiyata.db"
    SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"
    UPLOAD_FOLDER = BASE_DIR / "static" / "images"
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}