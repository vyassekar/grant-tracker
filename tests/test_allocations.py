"""Tests for the allocation-writing helpers (apply_allocation / apply_allocation_batch)
and the under-100%-allocated detector, all exercised against a real (temp) sqlite db
via the `db` fixture."""
import app as app_module
from tests.conftest import insert_department, insert_grant, insert_student


class TestApplyAllocation:
    def test_writes_a_new_allocation(self, db):
        student_id = insert_student(db)
        grant_id = insert_grant(db)

        error = app_module.apply_allocation(db, None, student_id, grant_id, "2026-01", "2026-03", "50")

        assert error is None
        rows = db.execute(
            "SELECT month, percent FROM allocations WHERE student_id = ? ORDER BY month", (student_id,)
        ).fetchall()
        assert [(r["month"], r["percent"]) for r in rows] == [
            ("2026-01", 50),
            ("2026-02", 50),
            ("2026-03", 50),
        ]

    def test_rejects_over_100_percent_against_another_grant(self, db):
        student_id = insert_student(db)
        grant_a = insert_grant(db, name="Grant A")
        grant_b = insert_grant(db, name="Grant B")
        app_module.apply_allocation(db, None, student_id, grant_a, "2026-01", "2026-01", "70")

        error = app_module.apply_allocation(db, None, student_id, grant_b, "2026-01", "2026-01", "40")

        assert error is not None
        assert "over 100%" in error
        # Nothing should have been written for grant_b.
        total_b = db.execute(
            "SELECT COUNT(*) AS n FROM allocations WHERE student_id = ? AND grant_id = ?", (student_id, grant_b)
        ).fetchone()["n"]
        assert total_b == 0

    def test_percent_zero_clears_the_range(self, db):
        student_id = insert_student(db)
        grant_id = insert_grant(db)
        app_module.apply_allocation(db, None, student_id, grant_id, "2026-01", "2026-02", "80")

        error = app_module.apply_allocation(db, None, student_id, grant_id, "2026-01", "2026-02", "0")

        assert error is None
        remaining = db.execute(
            "SELECT COUNT(*) AS n FROM allocations WHERE student_id = ? AND grant_id = ?", (student_id, grant_id)
        ).fetchone()["n"]
        assert remaining == 0

    def test_rejects_unknown_student(self, db):
        grant_id = insert_grant(db)
        error = app_module.apply_allocation(db, None, 999999, grant_id, "2026-01", "2026-01", "50")
        assert error == "Select a valid student and grant."

    def test_rejects_unknown_grant(self, db):
        student_id = insert_student(db)
        error = app_module.apply_allocation(db, None, student_id, 999999, "2026-01", "2026-01", "50")
        assert error == "Select a valid student and grant."

    def test_rejects_end_before_start(self, db):
        student_id = insert_student(db)
        grant_id = insert_grant(db)
        error = app_module.apply_allocation(db, None, student_id, grant_id, "2026-03", "2026-01", "50")
        assert "before the start month" in error

    def test_rejects_percent_over_100(self, db):
        student_id = insert_student(db)
        grant_id = insert_grant(db)
        error = app_module.apply_allocation(db, None, student_id, grant_id, "2026-01", "2026-01", "150")
        assert "between 0 and 100" in error

    def test_scenario_allocations_are_isolated_from_live(self, db):
        student_id = insert_student(db)
        grant_id = insert_grant(db)
        scenario_id = db.execute("INSERT INTO scenarios (name, created_at) VALUES (?, ?)", ("Test", "2026-01-01T00:00:00")).lastrowid

        error = app_module.apply_allocation(db, scenario_id, student_id, grant_id, "2026-01", "2026-01", "100")

        assert error is None
        live_count = db.execute(
            "SELECT COUNT(*) AS n FROM allocations WHERE student_id = ? AND scenario_id IS NULL", (student_id,)
        ).fetchone()["n"]
        scenario_count = db.execute(
            "SELECT COUNT(*) AS n FROM allocations WHERE student_id = ? AND scenario_id = ?", (student_id, scenario_id)
        ).fetchone()["n"]
        assert live_count == 0
        assert scenario_count == 1


class TestApplyAllocationBatch:
    def test_writes_multiple_grants_at_once(self, db):
        student_id = insert_student(db)
        grant_a = insert_grant(db, name="Grant A")
        grant_b = insert_grant(db, name="Grant B")

        error = app_module.apply_allocation_batch(
            db, None, student_id, [(grant_a, "60"), (grant_b, "40")], "2026-01", "2026-01"
        )

        assert error is None
        rows = {
            r["grant_id"]: r["percent"]
            for r in db.execute("SELECT grant_id, percent FROM allocations WHERE student_id = ?", (student_id,))
        }
        assert rows == {grant_a: 60, grant_b: 40}

    def test_rebalance_in_one_call_that_would_fail_sequentially(self, db):
        """This is the whole reason apply_allocation_batch exists instead of just
        calling apply_allocation twice: raising grant B while lowering grant A only
        works if both changes are validated together."""
        student_id = insert_student(db)
        grant_a = insert_grant(db, name="Grant A")
        grant_b = insert_grant(db, name="Grant B")
        app_module.apply_allocation(db, None, student_id, grant_a, "2026-01", "2026-01", "100")

        # Sequentially, raising grant_b to 50 first would fail (100 + 50 > 100).
        error = app_module.apply_allocation_batch(
            db, None, student_id, [(grant_a, "50"), (grant_b, "50")], "2026-01", "2026-01"
        )

        assert error is None
        rows = {
            r["grant_id"]: r["percent"]
            for r in db.execute("SELECT grant_id, percent FROM allocations WHERE student_id = ?", (student_id,))
        }
        assert rows == {grant_a: 50, grant_b: 50}

    def test_rejects_batch_total_over_100_against_other_grants(self, db):
        student_id = insert_student(db)
        grant_a = insert_grant(db, name="Grant A")
        grant_b = insert_grant(db, name="Grant B")
        grant_c = insert_grant(db, name="Grant C")
        app_module.apply_allocation(db, None, student_id, grant_a, "2026-01", "2026-01", "70")

        error = app_module.apply_allocation_batch(
            db, None, student_id, [(grant_b, "20"), (grant_c, "20")], "2026-01", "2026-01"
        )

        assert error is not None
        assert "over 100%" in error
        # Nothing from the rejected batch should have been written.
        for gid in (grant_b, grant_c):
            n = db.execute(
                "SELECT COUNT(*) AS n FROM allocations WHERE student_id = ? AND grant_id = ?", (student_id, gid)
            ).fetchone()["n"]
            assert n == 0

    def test_rejects_unknown_grant_in_batch(self, db):
        student_id = insert_student(db)
        error = app_module.apply_allocation_batch(db, None, student_id, [(999999, "50")], "2026-01", "2026-01")
        assert error == "Select a valid grant."

    def test_rejects_unknown_student(self, db):
        grant_id = insert_grant(db)
        error = app_module.apply_allocation_batch(db, None, 999999, [(grant_id, "50")], "2026-01", "2026-01")
        assert error == "Select a valid student."

    def test_empty_batch_clears_nothing_and_succeeds(self, db):
        student_id = insert_student(db)
        error = app_module.apply_allocation_batch(db, None, student_id, [], "2026-01", "2026-01")
        assert error is None


class TestUnderAllocatedMonths:
    def test_none_grid_is_empty(self):
        assert app_module.under_allocated_months(None) == []

    def test_flags_chargeable_months_under_100(self):
        grid = {
            "month_labels": ["Jan 2026", "Feb 2026"],
            "totals": [100, 60],
            "months_chargeable": [True, True],
        }
        assert app_module.under_allocated_months(grid) == [("Feb 2026", 60)]

    def test_ignores_non_chargeable_months_even_if_under_100(self):
        grid = {
            "month_labels": ["Jan 2026"],
            "totals": [0],
            "months_chargeable": [False],
        }
        assert app_module.under_allocated_months(grid) == []

    def test_no_under_allocated_months_is_empty(self):
        grid = {
            "month_labels": ["Jan 2026", "Feb 2026"],
            "totals": [100, 100],
            "months_chargeable": [True, True],
        }
        assert app_module.under_allocated_months(grid) == []

    def test_full_grid_from_a_real_allocation(self, db):
        department_id = insert_department(db)
        student_id = insert_student(db, department_id=department_id)
        grant_id = insert_grant(db)
        app_module.apply_allocation(db, None, student_id, grant_id, "2026-01", "2026-03", "50")

        grid = app_module.student_allocation_grid(student_id, None)

        assert app_module.under_allocated_months(grid) == [
            ("Jan 2026", 50),
            ("Feb 2026", 50),
            ("Mar 2026", 50),
        ]
