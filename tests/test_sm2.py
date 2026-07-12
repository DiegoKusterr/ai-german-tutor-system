from datetime import date

from learning_app.sm2 import SM2State, review_sm2


def test_sm2_progression_for_successful_reviews() -> None:
    initial = SM2State(due_date=date(2026, 3, 9))
    first = review_sm2(initial, quality=5, review_day=date(2026, 3, 9))
    second = review_sm2(first, quality=5, review_day=date(2026, 3, 10))
    third = review_sm2(second, quality=4, review_day=date(2026, 3, 16))

    assert first.repetitions == 1
    assert first.interval_days == 1
    assert second.repetitions == 2
    assert second.interval_days == 6
    assert third.repetitions == 3
    assert third.interval_days >= 6
    assert third.easiness >= 1.3


def test_sm2_lapse_resets_repetitions() -> None:
    state = SM2State(easiness=2.6, interval_days=10, repetitions=4, due_date=date(2026, 3, 9))
    updated = review_sm2(state, quality=2, review_day=date(2026, 3, 9))

    assert updated.repetitions == 0
    assert updated.interval_days == 1
    assert updated.due_date == date(2026, 3, 10)
