from datetime import date

from src.scheduler.daily_check import _holiday_matches_today


def test_holiday_matches_fixed_date_by_month_and_day():
    assert _holiday_matches_today(
        holiday_date=date(2024, 3, 8),
        holiday_rrule=None,
        target_date=date(2026, 3, 8),
    )


def test_holiday_matches_yearly_rrule():
    assert _holiday_matches_today(
        holiday_date=date(2024, 2, 23),
        holiday_rrule="FREQ=YEARLY",
        target_date=date(2026, 2, 23),
    )


def test_holiday_does_not_match_other_day():
    assert not _holiday_matches_today(
        holiday_date=date(2024, 3, 8),
        holiday_rrule="FREQ=YEARLY",
        target_date=date(2026, 3, 9),
    )
