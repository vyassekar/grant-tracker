"""Route-level integration tests for the newest features: the add-student form's
optional initial allocation, faculty creation with an Excel import, and applying a
scenario to live data. These go through the real Flask routes (via the `client`
fixture) rather than calling helpers directly, so they also cover request
parsing/redirect/flash behavior.
"""
from io import BytesIO

import openpyxl

import app as app_module
from tests.conftest import insert_department, insert_grant, insert_student, open_faculty_db


def make_workbook(rows, headers=("Project Name", "PTA", "Award End Date", "Budget", "Balance")):
    """A minimal .xlsx (as bytes) matching the report format import_from_excel.py /
    the faculty-import route expects: a header row followed by data rows.

    `rows`' third column (index 2, "Award End Date" in the default header layout) is
    given as an ISO "YYYY-MM-DD" string for readability at call sites, and converted
    to a real datetime.datetime here -- build_grant_records() requires an actual
    datetime instance (isinstance(end_date, datetime.datetime)), matching how
    openpyxl reads genuine Excel date cells; a plain string in that cell (what you'd
    get from just writing the ISO string directly) is silently skipped as "not a
    date" by the real import code, same as a malformed report column would be.
    """
    import datetime

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(headers))
    for row in rows:
        row = list(row)
        if len(row) > 2 and isinstance(row[2], str):
            row[2] = datetime.datetime.fromisoformat(row[2])
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


class TestAddStudentInitialAllocation:
    def test_creates_student_with_no_allocation_when_none_given(self, client, faculty_slug):
        resp = client.post("/students/add", data={"name": "Ada Lovelace", "role": "student"}, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Ada Lovelace" in resp.data

    def test_creates_student_with_a_valid_initial_split(self, client, faculty_slug, db):
        grant_id = insert_grant(db, name="NSF Test Grant")

        resp = client.post(
            "/students/add",
            data={
                "name": "Grace Hopper",
                "role": "student",
                "grant_id[]": [str(grant_id)],
                "percent[]": ["60"],
                "month_start": "2026-01",
                "month_end": "2026-02",
            },
            follow_redirects=True,
        )

        assert resp.status_code == 200
        student = db.execute("SELECT id FROM students WHERE name = 'Grace Hopper'").fetchone()
        assert student is not None
        rows = db.execute(
            "SELECT month, percent FROM allocations WHERE student_id = ? ORDER BY month", (student["id"],)
        ).fetchall()
        assert [(r["month"], r["percent"]) for r in rows] == [("2026-01", 60), ("2026-02", 60)]

    def test_over_100_percent_split_rolls_back_the_whole_student(self, client, faculty_slug, db):
        grant_a = insert_grant(db, name="Grant A")
        grant_b = insert_grant(db, name="Grant B")

        resp = client.post(
            "/students/add",
            data={
                "name": "Rejected Student",
                "role": "student",
                "grant_id[]": [str(grant_a), str(grant_b)],
                "percent[]": ["70", "40"],
                "month_start": "2026-01",
                "month_end": "2026-01",
            },
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert b"over 100%" in resp.data
        # Neither the student nor any allocation should have been committed.
        assert db.execute("SELECT COUNT(*) AS n FROM students WHERE name = 'Rejected Student'").fetchone()["n"] == 0
        assert db.execute("SELECT COUNT(*) AS n FROM allocations").fetchone()["n"] == 0

    def test_split_across_two_grants_summing_to_100(self, client, faculty_slug, db):
        grant_a = insert_grant(db, name="Grant A")
        grant_b = insert_grant(db, name="Grant B")

        resp = client.post(
            "/students/add",
            data={
                "name": "Split Student",
                "role": "postdoc",
                "grant_id[]": [str(grant_a), str(grant_b)],
                "percent[]": ["50", "50"],
                "month_start": "2026-03",
                "month_end": "2026-03",
            },
            follow_redirects=True,
        )

        assert resp.status_code == 200
        student = db.execute("SELECT id FROM students WHERE name = 'Split Student'").fetchone()
        total = db.execute(
            "SELECT COALESCE(SUM(percent), 0) AS total FROM allocations WHERE student_id = ? AND month = '2026-03'",
            (student["id"],),
        ).fetchone()["total"]
        assert total == 100


class TestFacultyExcelImport:
    def test_import_creates_grants_and_transactions(self, client):
        workbook = make_workbook(
            [
                ["Physics Grant", "PTA-001", "2029-12-31", 100_000, 40_000],
                ["Bio Grant", "PTA-002", "2029-06-30", 50_000, 50_000],  # fully spent -> no transaction
            ]
        )

        resp = client.post(
            "/faculty/add",
            data={"name": "Excel Faculty", "workbook": (workbook, "report.xlsx")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert b"Imported 2 grant(s)" in resp.data

        imported_db = open_faculty_db(app_module.slugify("Excel Faculty"))
        grants = {r["name"]: r for r in imported_db.execute("SELECT * FROM grants")}
        assert grants["Physics Grant"]["total_amount_cents"] == 100_000 * 100
        physics_id = grants["Physics Grant"]["id"]
        spent = imported_db.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) AS n FROM transactions WHERE grant_id = ?", (physics_id,)
        ).fetchone()["n"]
        # budget - balance = 100_000 - 40_000 = 60_000 dollars spent.
        assert spent == 60_000 * 100
        bio_id = grants["Bio Grant"]["id"]
        bio_spent = imported_db.execute(
            "SELECT COUNT(*) AS n FROM transactions WHERE grant_id = ?", (bio_id,)
        ).fetchone()["n"]
        assert bio_spent == 0  # budget == balance -> no lump-sum transaction recorded
        imported_db.close()

    def test_faculty_still_created_when_workbook_has_no_matching_sheet(self, client):
        workbook = make_workbook(
            [["irrelevant", "data"]], headers=("Some", "Other", "Columns")
        )

        resp = client.post(
            "/faculty/add",
            data={"name": "Bad Sheet Faculty", "workbook": (workbook, "report.xlsx")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert b"Couldn" in resp.data  # "Couldn't find a matching report sheet..."
        assert app_module.slugify("Bad Sheet Faculty") in app_module.list_faculty()

    def test_faculty_still_created_when_file_is_not_a_workbook(self, client):
        garbage = BytesIO(b"this is not an xlsx file")

        resp = client.post(
            "/faculty/add",
            data={"name": "Garbage File Faculty", "workbook": (garbage, "report.xlsx")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert b"Couldn" in resp.data
        assert app_module.slugify("Garbage File Faculty") in app_module.list_faculty()

    def test_no_workbook_is_a_plain_faculty_creation(self, client):
        resp = client.post("/faculty/add", data={"name": "Plain Faculty"}, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Imported" not in resp.data
        assert app_module.slugify("Plain Faculty") in app_module.list_faculty()

    def test_duplicate_ptas_are_skipped_on_reimport(self, client):
        """Re-running an import for the same faculty shouldn't double-count grants
        already tagged with a given PTA. The web UI only offers an import at
        faculty-creation time, so this exercises import_grants_from_workbook()'s
        dedupe guard directly, by calling it twice against the same db -- the same
        rule import_from_excel.py's CLI relies on to be safely re-runnable.

        Note: `client` is only depended on for its DATA_DIR-to-tmp_path monkeypatch
        (see the `client` fixture) -- no request is made through it here, since
        mixing a manual test_request_context() with the test client's own
        (request-preserving) context management corrupts Flask's context stack.
        """

        class FakeUpload:
            filename = "report.xlsx"

            def __init__(self, workbook):
                self._workbook = workbook

            def read(self):
                return self._workbook.getvalue()

        slug = app_module.slugify("Reimport Faculty")
        app_module.init_db(app_module.faculty_db_path(slug))

        with app_module.app.test_request_context():
            from flask import session

            session["faculty_db"] = slug
            for _ in range(2):
                app_module.import_grants_from_workbook(
                    FakeUpload(make_workbook([["Physics Grant", "PTA-001", "2029-12-31", 100_000, 40_000]]))
                )

        imported_db = open_faculty_db(slug)
        count = imported_db.execute("SELECT COUNT(*) AS n FROM grants WHERE name = 'Physics Grant'").fetchone()["n"]
        assert count == 1
        imported_db.close()


class TestApplyScenarioToLive:
    def test_apply_replaces_live_allocations_with_scenario_allocations(self, client, faculty_slug, db):
        department_id = insert_department(db)
        student_id = insert_student(db, department_id=department_id)
        grant_id = insert_grant(db)
        app_module.apply_allocation(db, None, student_id, grant_id, "2026-01", "2026-01", "30")
        db.commit()

        scenario_id = db.execute(
            "INSERT INTO scenarios (name, created_at) VALUES (?, ?)", ("Bump to 80%", "2026-01-01T00:00:00")
        ).lastrowid
        db.execute(
            """INSERT INTO allocations (scenario_id, student_id, grant_id, month, percent)
               SELECT ?, student_id, grant_id, month, percent FROM allocations WHERE scenario_id IS NULL""",
            (scenario_id,),
        )
        app_module.apply_allocation(db, scenario_id, student_id, grant_id, "2026-01", "2026-01", "80")
        db.commit()

        resp = client.post(f"/scenarios/{scenario_id}/apply", follow_redirects=True)

        assert resp.status_code == 200
        live_percent = db.execute(
            "SELECT percent FROM allocations WHERE student_id = ? AND grant_id = ? AND scenario_id IS NULL",
            (student_id, grant_id),
        ).fetchone()["percent"]
        assert live_percent == 80

    def test_spending_risk_reflects_new_live_allocation_on_next_request(self, client, faculty_slug, db):
        """The projected personnel cost shown on the dashboard is always computed
        fresh from live allocations (see grant_allocation_grid) -- applying a
        scenario should change it on the very next page load, with no caching."""
        # $10,000/month stipend, zero tuition/fringe/overhead -> projected cost is
        # exactly the prorated stipend, making the expected dashboard figure exact.
        department_id = insert_department(db, stipend_cents=1_000_000, tuition_cents=0, fringe_rate_bps=0)
        student_id = insert_student(db, department_id=department_id, stipend_cents=1_000_000)
        grant_id = insert_grant(db, name="Recompute Grant", overhead_rate_bps=0)
        app_module.apply_allocation(db, None, student_id, grant_id, "2026-01", "2026-01", "10")
        db.commit()

        before = client.get("/").data
        assert b"$1000.00" in before  # 10% of $10,000/month

        scenario_id = db.execute(
            "INSERT INTO scenarios (name, created_at) VALUES (?, ?)", ("Bump", "2026-01-01T00:00:00")
        ).lastrowid
        app_module.apply_allocation(db, scenario_id, student_id, grant_id, "2026-01", "2026-01", "90")
        db.commit()
        client.post(f"/scenarios/{scenario_id}/apply", follow_redirects=True)

        after = client.get("/").data
        assert b"$9000.00" in after  # 90% of the same $10,000/month stipend
        assert b"$1000.00" not in after
