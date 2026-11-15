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
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

    # Dual AI Provider Configuration (Gemini & OpenAI)
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")