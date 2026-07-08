"""Shared pytest fixtures for the grant-tracker test suite.

Every fixture here is careful to never touch the real project's data/*.db files
(see the "Never test writes against a real faculty .db directly" rule in
CLAUDE.md) -- `client` monkeypatches app.DATA_DIR to a pytest tmp_path for the
duration of each test, so every faculty database created during a test run is
thrown away with the test's temp directory.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as app_module  # noqa: E402  (import after sys.path fixup)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A Flask test client backed by an isolated, throwaway data/ directory."""
    monkeypatch.setattr(app_module, "DATA_DIR", tmp_path / "data")
    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as test_client:
        yield test_client


@pytest.fixture
def faculty_slug(client):
    """Create a fresh faculty database through the real /faculty/add route (so the
    test client's session cookie ends up pointing at it, exactly like a real user
    flow) and return its slug."""
    resp = client.post("/faculty/add", data={"name": "Test Faculty"}, follow_redirects=True)
    assert resp.status_code == 200
    return app_module.slugify("Test Faculty")


@pytest.fixture
def db(client, faculty_slug):
    """Direct sqlite access to the faculty db `client`'s session already points at --
    for test setup (departments/grants/students/allocations) that would be tedious
    to build purely through form posts, and for assertions afterward.

    Deliberately a *plain* sqlite3 connection to the same file (not get_db(), and no
    Flask request/app context) so it can be freely interleaved with client.get()/
    client.post() calls within the same test -- pushing a test_request_context()
    that outlives a single call fights with the test client's own context
    management and corrupts Flask's context stack (see open_faculty_db() below).
    """
    connection = open_faculty_db(faculty_slug)
    yield connection
    connection.commit()
    connection.close()


def open_faculty_db(slug):
    """A plain, already-migrated sqlite3 connection to a faculty db's file, for test
    setup/assertions that need to run interleaved with `client` requests. Mirrors
    get_db()'s connection setup (row factory, foreign keys, migrate_db) without
    touching Flask's g/session/request-context machinery at all.

    isolation_level=None (autocommit) so every statement commits immediately --
    otherwise an uncommitted write left open on this connection (e.g. a test helper
    that doesn't call .commit()) holds a lock that a subsequent `client.post()` on
    its own separate connection (get_db() opens a fresh one per request) would
    block on, raising "database is locked".
    """
    connection = sqlite3.connect(app_module.faculty_db_path(slug), isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    app_module.migrate_db(connection)
    return connection


def insert_department(
    db,
    name="Test Department",
    stipend_cents=370000,
    tuition_cents=120000,
    fringe_rate_bps=2800,
    tuition_charged_in_summer=True,
):
    cur = db.execute(
        """INSERT INTO departments (name, stipend_cents_per_month, tuition_cents_per_month, fringe_rate_bps,
           tuition_charged_in_summer) VALUES (?, ?, ?, ?, ?)""",
        (name, stipend_cents, tuition_cents, fringe_rate_bps, 1 if tuition_charged_in_summer else 0),
    )
    return cur.lastrowid


def insert_grant(
    db,
    name="Test Grant",
    sponsor="Test Sponsor",
    total_amount_cents=100_000_00,
    start_date="2025-01-01",
    end_date="2027-12-31",
    overhead_rate_bps=5000,
    category="sponsored",
):
    cur = db.execute(
        """INSERT INTO grants (name, sponsor, total_amount_cents, start_date, end_date, overhead_rate_bps, category)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name, sponsor, total_amount_cents, start_date, end_date, overhead_rate_bps, category),
    )
    return cur.lastrowid


def insert_student(
    db,
    name="Test Student",
    department_id=None,
    role="student",
    stipend_cents=370000,
    start_date=None,
    expected_graduation=None,
):
    cur = db.execute(
        """INSERT INTO students (name, email, department_id, role, stipend_cents_per_month, start_date,
           expected_graduation) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name, "", department_id, role, stipend_cents, start_date, expected_graduation),
    )
    return cur.lastrowid


def insert_allocation(db, student_id, grant_id, month, percent, scenario_id=None):
    db.execute(
        "INSERT INTO allocations (scenario_id, student_id, grant_id, month, percent) VALUES (?, ?, ?, ?, ?)",
        (scenario_id, student_id, grant_id, month, percent),
    )


def insert_transaction(db, grant_id, tx_date, amount_cents, description=""):
    db.execute(
        "INSERT INTO transactions (grant_id, date, amount_cents, description) VALUES (?, ?, ?, ?)",
        (grant_id, tx_date, amount_cents, description),
    )
