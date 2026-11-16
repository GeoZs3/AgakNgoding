import sqlite3
from pathlib import Path
from flask import Flask
from config import Config
from database.connection import close_db, get_db, init_db
from services.auth_service import load_logged_in_user
from services.ai_taxonomy_service import (
    dispatch_ai_worker_for_pending_tasks,
    recover_stale_ai_tasks,
)
from routes.main import main_bp
from routes.auth import auth_bp
from routes.plants import plants_bp


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    init_db(app)

    # Pulihkan antrean taksonomi AI yang tertinggal saat restart
    db_path = Path(app.config["DATABASE_PATH"])
    conn = sqlite3.connect(db_path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    try:
        recover_stale_ai_tasks(
            conn,
            stale_timeout_seconds=int(app.config.get("AI_STALE_TIMEOUT_SECONDS", 120)),
        )
        has_pending = conn.execute(
            "SELECT 1 FROM ai_taxonomy_tasks WHERE status = 'pending' AND attempt_count < max_attempts LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    if has_pending and not app.config.get("TESTING"):
        dispatch_ai_worker_for_pending_tasks(
            db_path=db_path,
            gemini_api_key=app.config.get("GEMINI_API_KEY", ""),
            gemini_model=app.config.get("GEMINI_MODEL", "gemini-3.8-flash"),
            openai_api_key=app.config.get("OPENAI_API_KEY", ""),
            openai_model=app.config.get("OPENAI_MODEL", "gpt-4o-mini"),
        )

    @app.before_request
    def before_request():
        db = get_db()
        load_logged_in_user(db)

    app.teardown_appcontext(close_db)

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(plants_bp)

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=5000, debug=True)