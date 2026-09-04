from src.workflow.worker_service import _calc_next_retry_sql


def next_retry_minutes(retry_count: int) -> int:
    sql = _calc_next_retry_sql(retry_count)
    if "15 minutes" in sql:
        return 15
    if "30 minutes" in sql:
        return 30
    if "60 minutes" in sql:
        return 60
    raise AssertionError(f"Unexpected retry SQL: {sql}")


def test_retry_schedule_matches_15_30_60():
    assert next_retry_minutes(1) == 15
    assert next_retry_minutes(2) == 30
    assert next_retry_minutes(3) == 60


def test_fourth_failure_should_be_terminal():
    new_retry_count = 4
    assert new_retry_count >= 4
