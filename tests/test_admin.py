import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from werkzeug.security import generate_password_hash

from app import create_app


ROOT = Path(__file__).resolve().parents[1]


class AdminRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

        class TestConfig:
            SECRET_KEY = "admin-tests"
            DATABASE_PATH = Path(self.temp_dir.name) / "test.db"
            SCHEMA_PATH = ROOT / "database" / "schema.sql"
            UPLOAD_FOLDER = Path(self.temp_dir.name) / "images"
            ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

        self.config = TestConfig
        self.app = create_app(self.config)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self._seed_database()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _seed_database(self):
        with closing(sqlite3.connect(self.config.DATABASE_PATH)) as db:
            with db:
                db.execute("PRAGMA foreign_keys = ON")
                db.executemany(
                    "INSERT INTO managers (code, name, is_plant_manager) VALUES (?, ?, 1)",
                    [("P1", "Penanggung Jawab P1"), ("P2", "Penanggung Jawab P2")],
                )
                db.execute(
                    """
                    INSERT INTO users (
                        username, password_hash, full_name, role, manager_code,
                        is_active, is_admin, can_edit_plants
                    )
                    VALUES (?, ?, ?, 'p_manager', 'P1', 1, 1, 1)
                    """,
                    ("P1", generate_password_hash("password1"), "Admin P1"),
                )
                type_id = db.execute(
                    "INSERT INTO plant_types (code, name) VALUES ('HIAS', 'Tanaman Hias')"
                ).lastrowid
                sector_id = db.execute(
                    "INSERT INTO sectors (code, name) VALUES ('GB', 'Gedung Baru')"
                ).lastrowid
                subsector_id = db.execute(
                    """
                    INSERT INTO subsectors (sector_id, code, name)
                    VALUES (?, 'TS01', 'Taman Siswa')
                    """,
                    (sector_id,),
                ).lastrowid
                db.execute(
                    """
                    INSERT INTO plants (
                        uid, plant_code, subsector_seq, name, quantity, status,
                        plant_type_id, subsector_id, manager_code
                    )
                    VALUES (?, 'GB-TS01-001-HIAS-P1', 1, 'Mawar', 4, 'Hidup', ?, ?, 'P1')
                    """,
                    (str(uuid.uuid4()), type_id, subsector_id),
                )

    def _login(self, username="P1", password="password1"):
        return self.client.post(
            "/login",
            data={"username": username, "password": password},
        )

    def _csrf_token(self):
        self.client.get("/admin/")
        with self.client.session_transaction() as session:
            return session["admin_csrf_token"]

    def _create_superadmin(self):
        with closing(sqlite3.connect(self.config.DATABASE_PATH)) as db:
            with db:
                cursor = db.execute(
                    """
                    INSERT INTO users (
                        username, password_hash, full_name, role, is_active,
                        is_admin, is_superadmin, can_edit_plants
                    )
                    VALUES ('ROOT', ?, 'Admin Utama', 'guru', 1, 1, 1, 1)
                    """,
                    (generate_password_hash("rootpass1"),),
                )
                return cursor.lastrowid

    def test_admin_dashboard_reports_inventory_and_active_manager(self):
        self._login()
        response = self.client.get("/admin/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Persentase kategori tanaman", response.data)
        self.assertIn(b"100.0%", response.data)
        self.assertIn(b"AKTIF", response.data)

    def test_public_home_has_a_separate_monitor_login_button(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Login Monitor", response.data)
        self.assertIn(b"/admin/login", response.data)

    def test_logged_in_admin_sees_admin_and_password_navigation(self):
        self._login()
        response = self.client.get("/?masuk=1")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Admin", response.data)
        self.assertIn(b"Ganti Password", response.data)

    def test_monitor_login_rejects_non_admin_accounts(self):
        with closing(sqlite3.connect(self.config.DATABASE_PATH)) as db:
            with db:
                db.execute(
                    """
                    INSERT INTO users (
                        username, password_hash, full_name, role, manager_code,
                        is_active, can_edit_plants
                    )
                    VALUES ('P2', ?, 'Pengelola P2', 'p_manager', 'P2', 1, 1)
                    """,
                    (generate_password_hash("password2"),),
                )

        response = self.client.post(
            "/admin/login",
            data={"username": "P2", "password": "password2"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Akun administrator tidak ditemukan", response.data)

    def test_admin_can_create_p_account_with_edit_permission(self):
        self._login()
        csrf_token = self._csrf_token()

        response = self.client.post(
            "/admin/accounts",
            data={
                "_csrf_token": csrf_token,
                "username": "P2",
                "full_name": "Pengelola P2",
                "password": "password2",
                "role": "p_manager",
                "manager_code": "P2",
                "can_edit_plants": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        with closing(sqlite3.connect(self.config.DATABASE_PATH)) as db:
            user = db.execute(
                """
                SELECT role, manager_code, is_admin, can_edit_plants
                FROM users WHERE username = 'P2'
                """
            ).fetchone()
        self.assertEqual(user, ("p_manager", "P2", 0, 1))

    def test_admin_can_create_another_admin(self):
        self._login()
        csrf_token = self._csrf_token()

        response = self.client.post(
            "/admin/accounts",
            data={
                "_csrf_token": csrf_token,
                "username": "P2",
                "full_name": "Admin P2",
                "password": "password2",
                "role": "admin",
            },
        )

        self.assertEqual(response.status_code, 302)
        with closing(sqlite3.connect(self.config.DATABASE_PATH)) as db:
            account = db.execute(
                "SELECT role, is_admin, can_edit_plants FROM users WHERE username = 'P2'"
            ).fetchone()
        self.assertEqual(account, ("guru", 1, 1))

    def test_admin_can_login_and_create_an_admin(self):
        self._create_superadmin()
        response = self.client.post(
            "/admin/login",
            data={"username": "ROOT", "password": "rootpass1"},
        )
        self.assertEqual(response.status_code, 302)

        csrf_token = self._csrf_token()
        self.client.post(
            "/admin/accounts",
            data={
                "_csrf_token": csrf_token,
                "username": "P2",
                "full_name": "Admin P2",
                "password": "password2",
                "role": "admin",
            },
        )

        with closing(sqlite3.connect(self.config.DATABASE_PATH)) as db:
            account = db.execute(
                "SELECT role, is_admin, is_superadmin FROM users WHERE username = 'P2'"
            ).fetchone()
        self.assertEqual(account, ("guru", 1, 0))

    def test_admin_can_demote_another_admin_when_another_admin_remains(self):
        superadmin_id = self._create_superadmin()
        self.client.post(
            "/admin/login",
            data={"username": "ROOT", "password": "rootpass1"},
        )
        csrf_token = self._csrf_token()

        response = self.client.post(
            f"/admin/accounts/{superadmin_id}",
            data={
                "_csrf_token": csrf_token,
                "username": "ROOT",
                "full_name": "Admin Utama",
                "role": "guru",
                "is_admin": "1",
                "is_active": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        with closing(sqlite3.connect(self.config.DATABASE_PATH)) as db:
            permissions = db.execute(
                "SELECT is_admin, is_superadmin FROM users WHERE id = ?",
                (superadmin_id,),
            ).fetchone()
        self.assertEqual(permissions, (0, 0))

    def test_admin_cannot_remove_the_last_admin(self):
        self._login()
        csrf_token = self._csrf_token()
        with closing(sqlite3.connect(self.config.DATABASE_PATH)) as db:
            admin_id = db.execute(
                "SELECT id FROM users WHERE username = 'P1'"
            ).fetchone()[0]

        response = self.client.post(
            f"/admin/accounts/{admin_id}",
            data={
                "_csrf_token": csrf_token,
                "username": "P1",
                "full_name": "Admin P1",
                "role": "p_manager",
                "manager_code": "P1",
                "can_edit_plants": "1",
                "is_active": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        with closing(sqlite3.connect(self.config.DATABASE_PATH)) as db:
            is_admin = db.execute(
                "SELECT is_admin FROM users WHERE id = ?",
                (admin_id,),
            ).fetchone()[0]
        self.assertEqual(is_admin, 1)

        response = self.client.post(
            f"/admin/accounts/{admin_id}/delete",
            data={"_csrf_token": csrf_token},
        )
        self.assertEqual(response.status_code, 302)
        with closing(sqlite3.connect(self.config.DATABASE_PATH)) as db:
            remaining = db.execute(
                "SELECT COUNT(*) FROM users WHERE id = ?",
                (admin_id,),
            ).fetchone()[0]
        self.assertEqual(remaining, 1)

    def test_p_can_edit_even_when_legacy_edit_flag_is_disabled(self):
        with closing(sqlite3.connect(self.config.DATABASE_PATH)) as db:
            with db:
                db.execute(
                    """
                    INSERT INTO users (
                        username, password_hash, full_name, role, manager_code,
                        is_active, can_edit_plants
                    )
                    VALUES ('P2', ?, 'Read Only P2', 'p_manager', 'P2', 1, 0)
                    """,
                    (generate_password_hash("password2"),),
                )

        response = self._login("P2", "password2")
        self.assertEqual(response.status_code, 302)
        editor_response = self.client.get("/tanaman/tambah")
        self.assertEqual(editor_response.status_code, 200)

    def test_user_can_change_own_password(self):
        self._login()
        response = self.client.get("/account/password")
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as session:
            csrf_token = session["password_csrf_token"]

        response = self.client.post(
            "/account/password",
            data={
                "_csrf_token": csrf_token,
                "current_password": "password1",
                "new_password": "newpass123",
                "confirm_password": "newpass123",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.client.get("/logout")
        response = self._login("P1", "newpass123")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin", response.headers["Location"])

    def test_admin_can_reset_and_delete_another_account(self):
        with closing(sqlite3.connect(self.config.DATABASE_PATH)) as db:
            with db:
                db.execute(
                    """
                    INSERT INTO users (
                        username, password_hash, full_name, role, manager_code,
                        is_active, can_edit_plants
                    )
                    VALUES ('P2', ?, 'Pengelola P2', 'p_manager', 'P2', 1, 1)
                    """,
                    (generate_password_hash("password2"),),
                )
                account_id = db.execute(
                    "SELECT id FROM users WHERE username = 'P2'"
                ).fetchone()[0]
        self._login()
        csrf_token = self._csrf_token()

        reset_page = self.client.get(f"/admin/accounts/{account_id}/password")
        self.assertEqual(reset_page.status_code, 200)
        response = self.client.post(
            f"/admin/accounts/{account_id}/password",
            data={
                "_csrf_token": csrf_token,
                "password": "resetpass123",
                "confirm_password": "resetpass123",
            },
        )
        self.assertEqual(response.status_code, 302)

        self.client.get("/logout")
        response = self._login("P2", "resetpass123")
        self.assertEqual(response.status_code, 302)
        self.client.get("/logout")
        self._login()
        csrf_token = self._csrf_token()
        response = self.client.post(
            f"/admin/accounts/{account_id}/delete",
            data={"_csrf_token": csrf_token},
        )
        self.assertEqual(response.status_code, 302)
        with closing(sqlite3.connect(self.config.DATABASE_PATH)) as db:
            account_count = db.execute(
                "SELECT COUNT(*) FROM users WHERE id = ?", (account_id,)
            ).fetchone()[0]
        self.assertEqual(account_count, 0)

    def test_admin_can_change_an_account_username_and_role(self):
        with closing(sqlite3.connect(self.config.DATABASE_PATH)) as db:
            with db:
                db.execute(
                    """
                    INSERT INTO users (
                        username, password_hash, full_name, role, manager_code,
                        is_active, can_edit_plants
                    )
                    VALUES ('P2', ?, 'Pengelola P2', 'p_manager', 'P2', 1, 0)
                    """,
                    (generate_password_hash("password2"),),
                )
                account_id = db.execute(
                    "SELECT id FROM users WHERE username = 'P2'"
                ).fetchone()[0]
        self._login()
        csrf_token = self._csrf_token()

        response = self.client.post(
            f"/admin/accounts/{account_id}",
            data={
                "_csrf_token": csrf_token,
                "username": "guru-baru",
                "full_name": "Guru Baru",
                "role": "guru",
                "is_active": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        with closing(sqlite3.connect(self.config.DATABASE_PATH)) as db:
            account = db.execute(
                "SELECT username, full_name, role, manager_code, is_admin, can_edit_plants "
                "FROM users WHERE id = ?",
                (account_id,),
            ).fetchone()
        self.assertEqual(account, ("guru-baru", "Guru Baru", "guru", None, 0, 1))


if __name__ == "__main__":
    unittest.main()
