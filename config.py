import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"

load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "adiwiyata-secret-key-2026")
    DATABASE_PATH = INSTANCE_DIR / "adiwiyata.db"
    SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"
    UPLOAD_FOLDER = BASE_DIR / "static" / "images"

    # Validasi Foto (Konten Aktual & Batas Ukuran)
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
    ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
    MAX_PHOTO_SIZE_BYTES = int(os.environ.get("MAX_PHOTO_SIZE_BYTES", 5 * 1024 * 1024))  # 5 MB

    # Dual AI Provider Configuration (Gemini & OpenAI)
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    # Ketahanan Proses AI Persisten
    AI_MAX_RETRIES = int(os.environ.get("AI_MAX_RETRIES", 3))
    AI_STALE_TIMEOUT_SECONDS = int(os.environ.get("AI_STALE_TIMEOUT_SECONDS", 120))