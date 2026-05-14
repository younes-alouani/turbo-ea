"""Unit tests for the pure helpers in ``risk_mitigation_task_service``.

DB-touching lifecycle paths are exercised by the API integration tests in
``tests/api/test_risk_mitigation_tasks.py``. Here we cover the
calendar-correct recurrence math and recurrence-rule edge cases.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services.risk_mitigation_task_service import (
    OCCURRENCE_STATUSES,
    RECURRENCE_UNITS,
    _add_months,
    compute_next_due,
)

# ---------------------------------------------------------------------------
# Calendar month math — Jan 31 + 1 month MUST land on Feb 28/29, not Mar 3
# ---------------------------------------------------------------------------


def test_add_months_simple_addition_within_year():
    assert _add_months(date(2026, 3, 15), 2) == date(2026, 5, 15)


def test_add_months_crosses_year_boundary():
    assert _add_months(date(2026, 11, 5), 3) == date(2027, 2, 5)


def test_add_months_clamps_to_last_day_of_short_month():
    # Jan 31 + 1 month → Feb 28 in a common year, Feb 29 in a leap year.
    assert _add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert _add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_add_months_clamps_31_to_30_day_month():
    assert _add_months(date(2026, 3, 31), 1) == date(2026, 4, 30)


def test_add_months_handles_year_jumps():
    assert _add_months(date(2026, 5, 14), 24) == date(2028, 5, 14)


# ---------------------------------------------------------------------------
# compute_next_due — dispatches across units
# ---------------------------------------------------------------------------


def test_compute_next_due_for_one_shot_returns_none():
    assert compute_next_due(date(2026, 5, 14), "none", 1) is None


def test_compute_next_due_for_days():
    assert compute_next_due(date(2026, 5, 14), "days", 1) == date(2026, 5, 15)
    assert compute_next_due(date(2026, 5, 14), "days", 30) == date(2026, 6, 13)


def test_compute_next_due_for_weeks():
    # 2 weeks = 14 days; spans a month boundary.
    assert compute_next_due(date(2026, 5, 14), "weeks", 2) == date(2026, 5, 28)
    assert compute_next_due(date(2026, 5, 28), "weeks", 1) == date(2026, 6, 4)


def test_compute_next_due_for_months():
    # The 6-month review use case from the user.
    assert compute_next_due(date(2026, 1, 15), "months", 6) == date(2026, 7, 15)


def test_compute_next_due_for_months_clamps_day():
    assert compute_next_due(date(2026, 1, 31), "months", 1) == date(2026, 2, 28)


def test_compute_next_due_for_years():
    assert compute_next_due(date(2026, 5, 14), "years", 1) == date(2027, 5, 14)
    # Leap-day rollover: Feb 29, 2024 + 1 year → Feb 28, 2025 (clamped).
    assert compute_next_due(date(2024, 2, 29), "years", 1) == date(2025, 2, 28)


def test_compute_next_due_rejects_unknown_unit():
    assert compute_next_due(date(2026, 5, 14), "fortnights", 1) is None


def test_compute_next_due_rejects_zero_interval():
    assert compute_next_due(date(2026, 5, 14), "days", 0) is None
    assert compute_next_due(date(2026, 5, 14), "months", 0) is None


# ---------------------------------------------------------------------------
# Vocabulary exports
# ---------------------------------------------------------------------------


def test_recurrence_units_include_none_and_all_intervals():
    assert RECURRENCE_UNITS == ("none", "days", "weeks", "months", "years")


def test_occurrence_statuses_have_three_terminals():
    assert OCCURRENCE_STATUSES == ("open", "done", "skipped")


# ---------------------------------------------------------------------------
# Guard against accidentally introducing fractional/negative intervals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "unit,interval",
    [
        ("days", -1),
        ("weeks", -2),
        ("months", -3),
        ("years", 0),
    ],
)
def test_compute_next_due_rejects_non_positive_intervals(unit: str, interval: int):
    assert compute_next_due(date(2026, 5, 14), unit, interval) is None
