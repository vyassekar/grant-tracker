"""Tests for grant balance/status and the spending-risk calculation, including the
user-tunable thresholds (Settings page)."""
from datetime import date, timedelta

import app as app_module
from tests.conftest import insert_grant, insert_transaction


def make_active_grant(**overrides):
    """A plain dict shaped like grant_with_balance()'s output, for feeding directly
    into grant_spending_risk() without needing a database at all."""
    grant = {
        "id": 1,
        "total_amount_cents": 100_000_00,
        "balance_cents": 100_000_00,
        "end_date": (date.today() + timedelta(days=365)).isoformat(),
        "status": "active",
    }
    grant.update(overrides)
    return grant


class TestGrantWithBalance:
    def test_computes_balance_and_status_from_transactions(self, db):
        grant_id = insert_grant(db, total_amount_cents=100_000, end_date="2099-12-31")
        insert_transaction(db, grant_id, "2026-01-01", 30_000)
        insert_transaction(db, grant_id, "2026-02-01", 5_000)
        row = db.execute("SELECT * FROM grants WHERE id = ?", (grant_id,)).fetchone()

        grant = app_module.grant_with_balance(row)

        assert grant["spent_cents"] == 35_000
        assert grant["balance_cents"] == 65_000
        assert grant["status"] == "active"

    def test_no_transactions_means_full_balance(self, db):
        grant_id = insert_grant(db, total_amount_cents=50_000, end_date="2099-12-31")
        row = db.execute("SELECT * FROM grants WHERE id = ?", (grant_id,)).fetchone()

        grant = app_module.grant_with_balance(row)

        assert grant["spent_cents"] == 0
        assert grant["balance_cents"] == 50_000


class TestCurrentMonthlyBurnCents:
    def test_no_grid_is_zero(self):
        assert app_module.current_monthly_burn_cents(None) == 0

    def test_uses_current_calendar_month_when_present(self):
        today_month = date.today().strftime("%Y-%m")
        grid = {"months": [today_month], "monthly_costs": [12345]}
        assert app_module.current_monthly_burn_cents(grid) == 12345

    def test_falls_back_to_nearest_future_month(self):
        # Grid only has data from a few months in the future.
        future = (date.today().replace(day=1) + timedelta(days=95)).strftime("%Y-%m")
        grid = {"months": [future], "monthly_costs": [999]}
        assert app_module.current_monthly_burn_cents(grid) == 999

    def test_all_months_in_the_past_is_zero(self):
        past = (date.today().replace(day=1) - timedelta(days=95)).strftime("%Y-%m")
        grid = {"months": [past], "monthly_costs": [999]}
        assert app_module.current_monthly_burn_cents(grid) == 0


class TestGrantSpendingRisk:
    OVERSPEND_BPS = 11500  # 115%
    UNDERSPEND_BPS = 6000  # 60%

    def risk(self, grant, grid):
        return app_module.grant_spending_risk(grant, grid, self.OVERSPEND_BPS, self.UNDERSPEND_BPS)

    def test_expired_grant_is_never_flagged(self):
        grant = make_active_grant(status="expired", balance_cents=-1000)
        assert self.risk(grant, None) is None

    def test_negative_balance_is_overspending(self):
        grant = make_active_grant(balance_cents=-1)
        assert self.risk(grant, None) == "overspending"

    def test_zero_balance_is_overspending(self):
        grant = make_active_grant(balance_cents=0)
        assert self.risk(grant, None) == "overspending"

    def test_no_burn_rate_is_underspending(self):
        grant = make_active_grant(balance_cents=100_000)
        assert self.risk(grant, None) == "underspending"

    def test_on_track_is_none(self):
        # 12 months remaining, burn * 12 should land between the two thresholds.
        today = date.today()
        end_date = date(today.year + 1, today.month, 1) - timedelta(days=1)
        grant = make_active_grant(balance_cents=120_000, end_date=end_date.isoformat())
        months_remaining = len(
            app_module.month_range(date(today.year, today.month, 1), date(end_date.year, end_date.month, 1))
        )
        # Burn rate chosen so projected spend is exactly 90% of balance -- comfortably
        # inside the default 60%-115% "on track" band.
        burn = int(120_000 * 0.9 / months_remaining)
        grid = {"months": [today.strftime("%Y-%m")], "monthly_costs": [burn]}
        assert self.risk(grant, grid) is None

    def test_projected_overspend_beyond_threshold_flags_overspending(self):
        today = date.today()
        grant = make_active_grant(balance_cents=1000, end_date=today.isoformat())
        # Only one month remaining (the current one); a burn rate far above the
        # remaining balance should trip the overspending threshold.
        grid = {"months": [today.strftime("%Y-%m")], "monthly_costs": [10_000]}
        assert self.risk(grant, grid) == "overspending"

    def test_projected_underspend_below_threshold_flags_underspending(self):
        today = date.today()
        end_date = date(today.year + 2, today.month, 1) - timedelta(days=1)
        grant = make_active_grant(balance_cents=10_000_000, end_date=end_date.isoformat())
        # Tiny burn rate relative to a huge balance and long remaining runway.
        grid = {"months": [today.strftime("%Y-%m")], "monthly_costs": [1]}
        assert self.risk(grant, grid) == "underspending"

    def test_thresholds_are_configurable(self):
        """The same grant/grid can flip categories purely based on the passed-in
        ratios -- this is the whole point of making them a Settings-page knob
        instead of a hardcoded constant."""
        today = date.today()
        grant = make_active_grant(balance_cents=100_000, end_date=today.isoformat())
        grid = {"months": [today.strftime("%Y-%m")], "monthly_costs": [90_000]}  # ratio == 0.9

        # Default thresholds (60%-115%): 0.9 is comfortably "on track".
        assert app_module.grant_spending_risk(grant, grid, 11500, 6000) is None
        # Tightening the overspend threshold below 90% should now flag it.
        assert app_module.grant_spending_risk(grant, grid, 8000, 6000) == "overspending"
        # Raising the underspend threshold above 90% should now flag it instead.
        assert app_module.grant_spending_risk(grant, grid, 11500, 9500) == "underspending"


class TestSettingsRoute:
    def test_defaults_match_previous_hardcoded_constants(self, db):
        settings = app_module.get_settings(db)
        assert settings == {"overspend_ratio_bps": 11500, "underspend_ratio_bps": 6000}

    def test_update_settings_persists_new_thresholds(self, client, faculty_slug):
        resp = client.post(
            "/settings/update",
            data={"overspend_ratio": "120", "underspend_ratio": "50"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"120.00" in resp.data
        assert b"50.00" in resp.data

    def test_rejects_underspend_at_or_above_overspend(self, client, faculty_slug):
        resp = client.post(
            "/settings/update",
            data={"overspend_ratio": "100", "underspend_ratio": "100"},
            follow_redirects=True,
        )
        assert b"must be lower than the overspending threshold" in resp.data
        # Unchanged from the default.
        assert b"115.00" in resp.data

    def test_rejects_negative_thresholds(self, client, faculty_slug):
        resp = client.post(
            "/settings/update",
            data={"overspend_ratio": "-10", "underspend_ratio": "50"},
            follow_redirects=True,
        )
        assert b"must be non-negative percentages" in resp.data
