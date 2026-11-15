from flask import Flask, render_template
from config import Config
from database.connection import close_db, get_db, init_db
from routes.auth import auth_bp
from routes.main import main_bp
from routes.plants import plants_bp
from services.auth_service import load_logged_in_user


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    # Inisialisasi otomatis file SQLite dan seluruh tabel jika belum ada
    init_db(app)

    @app.before_request
    def before_request():
        db = get_db()
        load_logged_in_user(db)

    app.teardown_appcontext(close_db)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(plants_bp)

    @app.errorhandler(404)
    def page_not_found(error):
        return render_template("404.html"), 404

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)