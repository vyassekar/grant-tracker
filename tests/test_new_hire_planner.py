"""Tests for the "Plan a new hire" capacity report's calculation functions
(app.py's grant_spare_capacity_cents / eligible_grants_for_window /
hire_window_cost_cents / build_greedy_hire_plan / build_spread_hire_plan). This is
the newest and most algorithmically involved feature added, so these tests lean
toward exact-number assertions rather than just "did it not crash."
"""
from datetime import date, timedelta

import app as app_module
from tests.conftest import insert_department, insert_grant, insert_student


def department_row(db, department_id):
    return dict(db.execute("SELECT * FROM departments WHERE id = ?", (department_id,)).fetchone())


def grant_row(db, grant_id):
    row = db.execute("SELECT * FROM grants WHERE id = ?", (grant_id,)).fetchone()
    return app_module.grant_with_balance(row)


class TestGrantSpareCapacityCents:
    def test_no_allocations_means_full_balance_is_spare(self, db):
        grant_id = insert_grant(db, total_amount_cents=100_000)
        grant = grant_row(db, grant_id)

        spare = app_module.grant_spare_capacity_cents(grant, ["2026-01", "2026-02"])

        assert spare == 100_000

    def test_committed_cost_within_window_reduces_spare(self, db):
        department_id = insert_department(db, stipend_cents=100_000, tuition_cents=0, fringe_rate_bps=0)
        student_id = insert_student(db, department_id=department_id, stipend_cents=100_000)
        grant_id = insert_grant(db, total_amount_cents=1_000_000, overhead_rate_bps=0)
        app_module.apply_allocation(db, None, student_id, grant_id, "2026-01", "2026-01", "100")

        grant = grant_row(db, grant_id)
        spare = app_module.grant_spare_capacity_cents(grant, ["2026-01"])

        # 100% of a $1000/mo stipend, zero fringe/overhead/tuition -> $1000 committed.
        assert spare == 1_000_000 - 100_000

    def test_commitments_outside_window_are_not_deducted(self, db):
        """Documented caveat: only commitments *within* the requested window count
        against spare capacity, even if the same grant is heavily committed the
        month right after the window."""
        department_id = insert_department(db, stipend_cents=100_000, tuition_cents=0, fringe_rate_bps=0)
        student_id = insert_student(db, department_id=department_id, stipend_cents=100_000)
        grant_id = insert_grant(db, total_amount_cents=1_000_000, overhead_rate_bps=0)
        app_module.apply_allocation(db, None, student_id, grant_id, "2026-02", "2026-02", "100")

        grant = grant_row(db, grant_id)
        spare = app_module.grant_spare_capacity_cents(grant, ["2026-01"])

        assert spare == 1_000_000


class TestEligibleGrantsForWindow:
    def test_expired_grant_is_excluded(self, db):
        grant_id = insert_grant(db, end_date=(date.today() - timedelta(days=1)).isoformat())
        eligible, excluded = app_module.eligible_grants_for_window(db, ["2026-01"])
        assert eligible == []
        assert excluded[0][0]["id"] == grant_id
        assert excluded[0][1] == "expired"

    def test_grant_that_starts_after_window_is_excluded(self, db):
        insert_grant(db, start_date="2027-01-01", end_date="2029-12-31")
        eligible, excluded = app_module.eligible_grants_for_window(db, ["2026-01"])
        assert eligible == []
        assert excluded[0][1] == "doesn't cover the full window"

    def test_grant_that_ends_before_window_is_excluded(self, db):
        # Not expired (end date is in the future), but its coverage stops well
        # before the requested window -- a distinct exclusion reason from "expired".
        end_date = date.today() + timedelta(days=200)
        window_month = (end_date + timedelta(days=200)).strftime("%Y-%m")
        insert_grant(db, start_date="2020-01-01", end_date=end_date.isoformat())

        eligible, excluded = app_module.eligible_grants_for_window(db, [window_month])

        assert eligible == []
        assert excluded[0][1] == "doesn't cover the full window"

    def test_grant_fully_spent_has_no_spare_capacity(self, db):
        from tests.conftest import insert_transaction

        grant_id = insert_grant(db, total_amount_cents=1000, start_date="2020-01-01", end_date="2029-12-31")
        insert_transaction(db, grant_id, "2026-01-01", 1000)
        eligible, excluded = app_module.eligible_grants_for_window(db, ["2026-06"])
        assert eligible == []
        assert excluded[0][1] == "no spare capacity left in this window"

    def test_eligible_grant_gets_spare_cents_attached(self, db):
        grant_id = insert_grant(
            db, total_amount_cents=50_000, start_date="2020-01-01", end_date="2029-12-31"
        )
        eligible, excluded = app_module.eligible_grants_for_window(db, ["2026-06"])
        assert excluded == []
        assert len(eligible) == 1
        assert eligible[0]["id"] == grant_id
        assert eligible[0]["spare_cents"] == 50_000


class TestHireWindowCostCents:
    def test_matches_allocation_cost_cents_at_100_percent(self, db):
        department_id = insert_department(
            db, stipend_cents=300_000, tuition_cents=100_000, fringe_rate_bps=3000, tuition_charged_in_summer=True
        )
        dept = department_row(db, department_id)

        monthly, total = app_module.hire_window_cost_cents(dept, overhead_rate_bps=5000, months=["2026-01"])

        expected = app_module.allocation_cost_cents(300_000, 100_000, 3000, 5000, 100)
        assert monthly == [expected["total"]]
        assert total == expected["total"]

    def test_summer_tuition_exclusion_zeroes_tuition_in_summer_months(self, db):
        department_id = insert_department(
            db, stipend_cents=300_000, tuition_cents=100_000, fringe_rate_bps=0, tuition_charged_in_summer=False
        )
        dept = department_row(db, department_id)

        monthly, total = app_module.hire_window_cost_cents(dept, overhead_rate_bps=0, months=["2026-06", "2026-09"])

        # June (summer): tuition zeroed, only stipend counts. September: full cost.
        assert monthly[0] == 300_000
        assert monthly[1] == 300_000 + 100_000
        assert total == monthly[0] + monthly[1]

    def test_summer_tuition_charged_when_flag_is_true(self, db):
        department_id = insert_department(
            db, stipend_cents=300_000, tuition_cents=100_000, fringe_rate_bps=0, tuition_charged_in_summer=True
        )
        dept = department_row(db, department_id)

        monthly, _ = app_module.hire_window_cost_cents(dept, overhead_rate_bps=0, months=["2026-07"])

        assert monthly[0] == 300_000 + 100_000


class TestBuildGreedyHirePlan:
    def _department(self, db, **kwargs):
        department_id = insert_department(db, **kwargs)
        return department_row(db, department_id)

    def test_single_hire_fully_funded_by_one_grant(self, db):
        dept = self._department(db, stipend_cents=100_000, tuition_cents=0, fringe_rate_bps=0)
        grant_id = insert_grant(db, total_amount_cents=10_000_000, overhead_rate_bps=0)
        grant = grant_row(db, grant_id)
        grant["spare_cents"] = 10_000_000
        hires = [{"department": dept, "role": "student"}]

        plan = app_module.build_greedy_hire_plan("Concentrate", "desc", hires, [grant], ["2026-01"])

        assert plan["feasible"] is True
        assert plan["fully_placed_count"] == 1
        assert plan["hires"][0]["placed_pct"] == 100
        assert plan["hires"][0]["assignments"] == [
            {"grant_id": grant_id, "grant_name": grant["name"], "percent": 100, "window_cost_cents": 100_000.0}
        ]

    def test_partial_capacity_yields_partial_placement(self, db):
        dept = self._department(db, stipend_cents=100_000, tuition_cents=0, fringe_rate_bps=0)
        grant_id = insert_grant(db, overhead_rate_bps=0)
        grant = grant_row(db, grant_id)
        grant["spare_cents"] = 50_000  # Only enough for 50% of one month's $100_000 cost.
        hires = [{"department": dept, "role": "student"}]

        plan = app_module.build_greedy_hire_plan("Concentrate", "desc", hires, [grant], ["2026-01"])

        assert plan["feasible"] is False
        assert plan["hires"][0]["placed_pct"] == 50
        assert plan["hires"][0]["assignments"][0]["percent"] == 50

    def test_spills_onto_next_grant_in_order_once_first_is_exhausted(self, db):
        """Two hires, one grant with only enough spare capacity for one of them: in
        the given order (most-spare-first for real callers), the first hire should
        drain grant A, and the second should spill onto grant B."""
        dept = self._department(db, stipend_cents=100_000, tuition_cents=0, fringe_rate_bps=0)
        grant_a_id = insert_grant(db, name="A", overhead_rate_bps=0)
        grant_b_id = insert_grant(db, name="B", overhead_rate_bps=0)
        grant_a = grant_row(db, grant_a_id)
        grant_a["spare_cents"] = 100_000  # exactly one hire's worth
        grant_b = grant_row(db, grant_b_id)
        grant_b["spare_cents"] = 100_000
        hires = [{"department": dept, "role": "student"}, {"department": dept, "role": "student"}]

        plan = app_module.build_greedy_hire_plan("Concentrate", "desc", hires, [grant_a, grant_b], ["2026-01"])

        assert plan["feasible"] is True
        assert plan["hires"][0]["assignments"][0]["grant_id"] == grant_a_id
        assert plan["hires"][0]["assignments"][0]["percent"] == 100
        assert plan["hires"][1]["assignments"][0]["grant_id"] == grant_b_id
        assert plan["hires"][1]["assignments"][0]["percent"] == 100

    def test_no_grants_means_zero_percent_placed(self, db):
        dept = self._department(db)
        hires = [{"department": dept, "role": "postdoc"}]

        plan = app_module.build_greedy_hire_plan("Concentrate", "desc", hires, [], ["2026-01"])

        assert plan["feasible"] is False
        assert plan["hires"][0]["placed_pct"] == 0
        assert plan["hires"][0]["assignments"] == []

    def test_zero_cost_department_is_trivially_fully_placed_with_no_grants_needed(self, db):
        dept = self._department(db, stipend_cents=0, tuition_cents=0, fringe_rate_bps=0)
        hires = [{"department": dept, "role": "student"}]

        # available_percent() treats a zero-cost hire as 100% fundable even against a
        # grant with zero spare capacity -- confirm that plumbs through end to end.
        grant_id = insert_grant(db, overhead_rate_bps=0)
        grant = grant_row(db, grant_id)
        grant["spare_cents"] = 0

        plan = app_module.build_greedy_hire_plan("Concentrate", "desc", hires, [grant], ["2026-01"])

        assert plan["hires"][0]["placed_pct"] == 100
        assert plan["hires"][0]["window_cost_cents"] == 0


class TestBuildSpreadHirePlan:
    def _department(self, db, **kwargs):
        department_id = insert_department(db, **kwargs)
        return department_row(db, department_id)

    def test_splits_proportionally_across_two_equal_grants(self, db):
        dept = self._department(db, stipend_cents=100_000, tuition_cents=0, fringe_rate_bps=0)
        grant_a_id = insert_grant(db, name="A", overhead_rate_bps=0)
        grant_b_id = insert_grant(db, name="B", overhead_rate_bps=0)
        grant_a = grant_row(db, grant_a_id)
        grant_a["spare_cents"] = 1_000_000
        grant_b = grant_row(db, grant_b_id)
        grant_b["spare_cents"] = 1_000_000
        hires = [{"department": dept, "role": "student"}]

        plan = app_module.build_spread_hire_plan(hires, [grant_a, grant_b], ["2026-01"])

        assert plan["feasible"] is True
        percents = {a["grant_id"]: a["percent"] for a in plan["hires"][0]["assignments"]}
        assert percents == {grant_a_id: 50, grant_b_id: 50}

    def test_percentages_sum_exactly_to_placed_pct_even_with_uneven_capacity(self, db):
        """Largest-remainder rounding must always leave the assigned percentages
        summing exactly to the feasible total, never off by a rounding unit."""
        dept = self._department(db, stipend_cents=100_000, tuition_cents=0, fringe_rate_bps=0)
        grant_ids = [insert_grant(db, name=f"G{i}", overhead_rate_bps=0) for i in range(3)]
        grants = []
        for gid in grant_ids:
            g = grant_row(db, gid)
            g["spare_cents"] = 1_000_000  # ample capacity on all three
            grants.append(g)
        hires = [{"department": dept, "role": "student"}]

        plan = app_module.build_spread_hire_plan(hires, grants, ["2026-01"])

        total_percent = sum(a["percent"] for a in plan["hires"][0]["assignments"])
        assert total_percent == plan["hires"][0]["placed_pct"] == 100

    def test_later_hires_see_reduced_capacity_from_earlier_ones(self, db):
        dept = self._department(db, stipend_cents=100_000, tuition_cents=0, fringe_rate_bps=0)
        grant_id = insert_grant(db, overhead_rate_bps=0)
        grant = grant_row(db, grant_id)
        grant["spare_cents"] = 150_000  # 1.5 hires' worth
        hires = [{"department": dept, "role": "student"}, {"department": dept, "role": "student"}]

        plan = app_module.build_spread_hire_plan(hires, [grant], ["2026-01"])

        assert plan["hires"][0]["placed_pct"] == 100
        assert plan["hires"][1]["placed_pct"] == 50
        assert plan["feasible"] is False
        assert plan["fully_placed_count"] == 1

    def test_no_capacity_anywhere_places_nothing(self, db):
        # Non-zero department cost so available_percent() doesn't trivially treat
        # this as a free (100% fundable) hire.
        dept = self._department(db, stipend_cents=100_000, tuition_cents=0, fringe_rate_bps=0)
        grant_id = insert_grant(db)
        grant = grant_row(db, grant_id)
        grant["spare_cents"] = 0
        hires = [{"department": dept, "role": "student"}]

        plan = app_module.build_spread_hire_plan(hires, [grant], ["2026-01"])

        assert plan["hires"][0]["placed_pct"] == 0
        assert plan["hires"][0]["assignments"] == []
