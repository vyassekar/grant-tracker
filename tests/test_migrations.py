"""Tests for migrate_db()'s on-the-fly schema upgrades. schema.sql only runs for a
brand-new faculty .db file (see init_db); every *existing* file has to pick up later
schema changes via migrate_db()'s idempotent ALTER TABLE / CREATE TABLE checks on
every connection. These tests build a deliberately old-shaped database by hand (the
columns/tables that predate the features added in this change) and confirm
migrate_db() brings it up to date without touching existing data, and is safe to run
more than once.
"""
import sqlite3

import app as app_module

# Schema as it existed before: departments.tuition_charged_in_summer, the settings
# table, and (older still) students.role/start_date/expected_graduation and
# grants.category. Deliberately minimal/old-shaped, not a copy of schema.sql.
LEGACY_SCHEMA = """
CREATE TABLE grants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    sponsor TEXT,
    total_amount_cents INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    overhead_rate_bps INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE TABLE departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    tuition_cents_per_month INTEGER NOT NULL DEFAULT 0,
    fringe_rate_bps INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    department_id INTEGER REFERENCES departments(id),
    stipend_cents_per_month INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grant_id INTEGER NOT NULL REFERENCES grants(id),
    date TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    description TEXT
);

CREATE TABLE scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id INTEGER REFERENCES scenarios(id),
    student_id INTEGER NOT NULL REFERENCES students(id),
    grant_id INTEGER NOT NULL REFERENCES grants(id),
    month TEXT NOT NULL,
    percent INTEGER NOT NULL
);
"""


def make_legacy_db(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(LEGACY_SCHEMA)
    dept_id = db.execute(
        "INSERT INTO departments (name, tuition_cents_per_month, fringe_rate_bps) VALUES (?, ?, ?)",
        ("Legacy Department", 100_000, 3000),
    ).lastrowid
    db.execute(
        "INSERT INTO students (name, department_id, stipend_cents_per_month) VALUES (?, ?, ?)",
        ("Legacy Student", dept_id, 350_000),
    )
    db.execute(
        "INSERT INTO grants (name, sponsor, total_amount_cents, start_date, end_date) VALUES (?, ?, ?, ?, ?)",
        ("Legacy Grant", "NSF", 100_000_00, "2020-01-01", "2029-12-31"),
    )
    db.commit()
    return db


class TestMigrateDb:
    def test_adds_department_columns_with_correct_defaults(self, tmp_path):
        db = make_legacy_db(tmp_path / "legacy.db")

        app_module.migrate_db(db)

        cols = {row["name"] for row in db.execute("PRAGMA table_info(departments)")}
        assert {"stipend_cents_per_month", "tuition_charged_in_summer"} <= cols
        row = db.execute("SELECT * FROM departments WHERE name = 'Legacy Department'").fetchone()
        assert row["stipend_cents_per_month"] == 0
        assert row["tuition_charged_in_summer"] == 1

    def test_adds_student_columns(self, tmp_path):
        db = make_legacy_db(tmp_path / "legacy.db")

        app_module.migrate_db(db)

        cols = {row["name"] for row in db.execute("PRAGMA table_info(students)")}
        assert {"expected_graduation", "start_date", "role"} <= cols
        row = db.execute("SELECT * FROM students WHERE name = 'Legacy Student'").fetchone()
        assert row["role"] == "student"
        assert row["start_date"] is None
        assert row["expected_graduation"] is None

    def test_adds_grant_category_column(self, tmp_path):
        db = make_legacy_db(tmp_path / "legacy.db")

        app_module.migrate_db(db)

        cols = {row["name"] for row in db.execute("PRAGMA table_info(grants)")}
        assert "category" in cols
        row = db.execute("SELECT * FROM grants WHERE name = 'Legacy Grant'").fetchone()
        assert row["category"] == "sponsored"

    def test_creates_settings_table_with_default_row(self, tmp_path):
        db = make_legacy_db(tmp_path / "legacy.db")

        app_module.migrate_db(db)

        row = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        assert row["overspend_ratio_bps"] == 11500
        assert row["underspend_ratio_bps"] == 6000

    def test_preserves_existing_data(self, tmp_path):
        db = make_legacy_db(tmp_path / "legacy.db")

        app_module.migrate_db(db)

        assert db.execute("SELECT COUNT(*) AS n FROM departments").fetchone()["n"] == 1
        assert db.execute("SELECT COUNT(*) AS n FROM students").fetchone()["n"] == 1
        assert db.execute("SELECT COUNT(*) AS n FROM grants").fetchone()["n"] == 1

    def test_is_idempotent_when_run_twice(self, tmp_path):
        db = make_legacy_db(tmp_path / "legacy.db")

        app_module.migrate_db(db)
        # A second call must not raise (duplicate ALTER/CREATE TABLE) and must not
        # touch the settings row that already exists.
        app_module.migrate_db(db)

        assert db.execute("SELECT COUNT(*) AS n FROM settings").fetchone()["n"] == 1

    def test_is_idempotent_on_an_already_current_schema(self, db):
        """The `db` fixture already goes through init_db() (fresh schema.sql), so this
        exercises migrate_db() against a fully up-to-date database -- should be a
        no-op, not an error."""
        app_module.migrate_db(db)
        app_module.migrate_db(db)
        assert db.execute("SELECT COUNT(*) AS n FROM settings").fetchone()["n"] == 1

    def test_runs_automatically_via_get_db_on_a_legacy_file(self, tmp_path, monkeypatch):
        """get_db() calls migrate_db() on every connection (see app.py) -- confirm
        that wiring, not just the migrate_db() function in isolation."""
        monkeypatch.setattr(app_module, "DATA_DIR", tmp_path / "data")
        (tmp_path / "data").mkdir()
        db = make_legacy_db(app_module.faculty_db_path("legacy-slug"))
        db.close()

        with app_module.app.test_request_context():
            from flask import session

            session["faculty_db"] = "legacy-slug"
            live_db = app_module.get_db()
            row = live_db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
            assert row["overspend_ratio_bps"] == 11500
