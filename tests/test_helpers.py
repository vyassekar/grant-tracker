"""Unit tests for the pure parsing/date/cost helpers in app.py -- no Flask request
context or database needed for any of these."""
from datetime import date, timedelta

import pytest

import app as app_module


class TestParseMoney:
    def test_parses_plain_dollar_amount(self):
        assert app_module.parse_money("12.34") == 1234

    def test_parses_whole_dollar_amount(self):
        assert app_module.parse_money("10") == 1000

    def test_zero_is_valid(self):
        assert app_module.parse_money("0") == 0

    def test_strips_surrounding_whitespace(self):
        assert app_module.parse_money("  5.50  ") == 550

    def test_rejects_negative(self):
        assert app_module.parse_money("-5") is None

    def test_rejects_non_numeric(self):
        assert app_module.parse_money("not a number") is None

    def test_rejects_empty_string(self):
        assert app_module.parse_money("") is None

    def test_rejects_none(self):
        assert app_module.parse_money(None) is None


class TestParseRate:
    def test_parses_percent_into_bps(self):
        assert app_module.parse_rate("54.5") == 5450

    def test_zero_is_valid(self):
        assert app_module.parse_rate("0") == 0

    def test_rejects_negative(self):
        assert app_module.parse_rate("-1") is None

    def test_rejects_non_numeric(self):
        assert app_module.parse_rate("garbage") is None


class TestParseDate:
    def test_parses_valid_iso_date(self):
        assert app_module.parse_date("2026-07-08") == date(2026, 7, 8)

    def test_rejects_invalid_format(self):
        assert app_module.parse_date("07/08/2026") is None

    def test_rejects_empty_string(self):
        assert app_module.parse_date("") is None


class TestParseOptionalDate:
    def test_blank_is_valid_and_none(self):
        parsed, ok = app_module.parse_optional_date("")
        assert parsed is None
        assert ok is True

    def test_missing_is_valid_and_none(self):
        parsed, ok = app_module.parse_optional_date(None)
        assert parsed is None
        assert ok is True

    def test_valid_date_parses(self):
        parsed, ok = app_module.parse_optional_date("2026-01-15")
        assert parsed == date(2026, 1, 15)
        assert ok is True

    def test_garbage_is_invalid(self):
        parsed, ok = app_module.parse_optional_date("garbage")
        assert parsed is None
        assert ok is False


class TestParseMonth:
    def test_parses_year_month_to_first_of_month(self):
        assert app_module.parse_month("2026-03") == date(2026, 3, 1)

    def test_rejects_missing_month_component(self):
        assert app_module.parse_month("2026") is None

    def test_rejects_garbage(self):
        assert app_module.parse_month("garbage") is None


class TestMonthRange:
    def test_single_month(self):
        assert app_module.month_range(date(2026, 3, 1), date(2026, 3, 1)) == ["2026-03"]

    def test_spans_year_boundary(self):
        assert app_module.month_range(date(2025, 11, 1), date(2026, 2, 1)) == [
            "2025-11",
            "2025-12",
            "2026-01",
            "2026-02",
        ]


class TestMonthEnd:
    def test_leap_year_february(self):
        assert app_module.month_end(date(2024, 2, 1)) == date(2024, 2, 29)

    def test_non_leap_year_february(self):
        assert app_module.month_end(date(2026, 2, 1)) == date(2026, 2, 28)

    def test_thirty_day_month(self):
        assert app_module.month_end(date(2026, 4, 1)) == date(2026, 4, 30)


class TestIsSummerMonth:
    @pytest.mark.parametrize("month_str", ["2026-06", "2026-07", "2026-08"])
    def test_summer_months_are_true(self, month_str):
        assert app_module.is_summer_month(month_str) is True

    @pytest.mark.parametrize("month_str", ["2026-01", "2026-05", "2026-09", "2026-12"])
    def test_non_summer_months_are_false(self, month_str):
        assert app_module.is_summer_month(month_str) is False


class TestGrantStatus:
    def test_past_end_date_is_expired(self):
        past = (date.today() - timedelta(days=1)).isoformat()
        assert app_module.grant_status(past) == "expired"

    def test_end_date_today_is_not_yet_expired(self):
        assert app_module.grant_status(date.today().isoformat()) == "expiring-soon"

    def test_within_expiring_soon_window(self):
        soon = (date.today() + timedelta(days=30)).isoformat()
        assert app_module.grant_status(soon) == "expiring-soon"

    def test_exactly_at_expiring_soon_boundary(self):
        boundary = (date.today() + timedelta(days=app_module.EXPIRING_SOON_DAYS)).isoformat()
        assert app_module.grant_status(boundary) == "expiring-soon"

    def test_just_past_expiring_soon_boundary_is_active(self):
        past_boundary = (date.today() + timedelta(days=app_module.EXPIRING_SOON_DAYS + 1)).isoformat()
        assert app_module.grant_status(past_boundary) == "active"

    def test_far_future_is_active(self):
        far = (date.today() + timedelta(days=400)).isoformat()
        assert app_module.grant_status(far) == "active"


class TestIsChargeable:
    def test_no_window_is_always_chargeable(self):
        assert app_module.is_chargeable("2026-03", None, None) is True

    def test_month_before_start_date_not_chargeable(self):
        assert app_module.is_chargeable("2026-01", "2026-02-15", None) is False

    def test_month_containing_start_date_is_chargeable(self):
        # Mid-month start still charges the whole month it falls in.
        assert app_module.is_chargeable("2026-02", "2026-02-15", None) is True

    def test_month_after_start_date_is_chargeable(self):
        assert app_module.is_chargeable("2026-03", "2026-02-15", None) is True

    def test_month_after_graduation_not_chargeable(self):
        assert app_module.is_chargeable("2026-06", None, "2026-05-15") is False

    def test_month_containing_graduation_is_chargeable(self):
        assert app_module.is_chargeable("2026-05", None, "2026-05-15") is True

    def test_month_within_both_bounds_is_chargeable(self):
        assert app_module.is_chargeable("2026-03", "2026-01-01", "2026-05-31") is True

    def test_month_outside_both_bounds_not_chargeable(self):
        assert app_module.is_chargeable("2027-01", "2026-01-01", "2026-05-31") is False


class TestAllocationCostCents:
    def test_full_effort_breakdown(self):
        # $3000/mo stipend, $1000/mo tuition, 30% fringe, 50% overhead, 100% effort.
        cost = app_module.allocation_cost_cents(300_000, 100_000, 3000, 5000, 100)
        assert cost["stipend"] == 300_000
        assert cost["tuition"] == 100_000
        assert cost["fringe"] == 90_000  # 30% of stipend
        # Overhead applies to stipend + fringe only, NOT tuition (MTDC-style exclusion).
        assert cost["overhead"] == 195_000  # 50% of (300_000 + 90_000)
        assert cost["total"] == 300_000 + 100_000 + 90_000 + 195_000

    def test_prorated_by_percent(self):
        cost = app_module.allocation_cost_cents(300_000, 100_000, 3000, 5000, 50)
        assert cost["stipend"] == 150_000
        assert cost["tuition"] == 50_000

    def test_zero_percent_is_all_zero(self):
        cost = app_module.allocation_cost_cents(300_000, 100_000, 3000, 5000, 0)
        assert cost == {"stipend": 0, "tuition": 0, "fringe": 0, "overhead": 0, "total": 0}

    def test_zero_rates_is_all_zero(self):
        cost = app_module.allocation_cost_cents(0, 0, 0, 0, 100)
        assert cost == {"stipend": 0, "tuition": 0, "fringe": 0, "overhead": 0, "total": 0}


class TestEmptyAndAddCostBreakdown:
    def test_empty_cost_breakdown_is_all_zero(self):
        assert app_module.empty_cost_breakdown() == {
            "stipend": 0,
            "tuition": 0,
            "fringe": 0,
            "overhead": 0,
            "total": 0,
        }

    def test_add_cost_breakdown_accumulates_each_key(self):
        totals = app_module.empty_cost_breakdown()
        app_module.add_cost_breakdown(totals, {"stipend": 10, "tuition": 20, "fringe": 3, "overhead": 4, "total": 37})
        app_module.add_cost_breakdown(totals, {"stipend": 5, "tuition": 0, "fringe": 1, "overhead": 2, "total": 8})
        assert totals == {"stipend": 15, "tuition": 20, "fringe": 4, "overhead": 6, "total": 45}


class TestAvailablePercent:
    def test_zero_cost_hire_is_trivially_fully_fundable(self):
        assert app_module.available_percent(0, 0) == 100
        assert app_module.available_percent(-500, 0) == 100

    def test_ample_spare_capacity_is_fully_fundable(self):
        assert app_module.available_percent(1_000_000, 100_000) == 100

    def test_partial_capacity_floors_to_whole_percent(self):
        # 55_000 / 100_000 * 100 = 55.0 exactly, but check a non-exact case too.
        assert app_module.available_percent(55_000, 100_000) == 55
        assert app_module.available_percent(54_999, 100_000) == 54

    def test_no_spare_capacity_is_zero(self):
        assert app_module.available_percent(0, 100_000) == 0

    def test_negative_spare_capacity_clamps_to_zero(self):
        assert app_module.available_percent(-1000, 100_000) == 0
