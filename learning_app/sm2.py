from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

FIXED_INTERVAL_SEQUENCE = (1, 3, 7, 14, 30)


@dataclass(slots=True)
class SM2State:
    easiness: float = 2.5
    interval_days: int = 0
    repetitions: int = 0
    due_date: date = date.today()


def review_sm2(state: SM2State, quality: int, review_day: date | None = None) -> SM2State:
    quality = max(0, min(5, int(quality)))
    today = review_day or date.today()

    easiness = state.easiness + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    easiness = max(1.3, round(easiness, 2))

    if quality < 3:
        repetitions = 0
        interval_days = 1
    else:
        repetitions = state.repetitions + 1
        if repetitions == 1:
            interval_days = 1
        elif repetitions == 2:
            interval_days = 6
        else:
            interval_days = max(1, round(state.interval_days * easiness))

    due_date = today + timedelta(days=interval_days)
    return SM2State(
        easiness=easiness,
        interval_days=interval_days,
        repetitions=repetitions,
        due_date=due_date,
    )


def review_fixed_intervals(state: SM2State, quality: int, review_day: date | None = None) -> SM2State:
    quality = max(0, min(5, int(quality)))
    today = review_day or date.today()

    # Baseline schedule: fixed interval ladder with only pass/fail progression.
    if quality < 3:
        repetitions = 0
        interval_days = FIXED_INTERVAL_SEQUENCE[0]
    else:
        repetitions = min(state.repetitions + 1, len(FIXED_INTERVAL_SEQUENCE))
        interval_days = FIXED_INTERVAL_SEQUENCE[max(0, repetitions - 1)]

    due_date = today + timedelta(days=interval_days)
    return SM2State(
        easiness=round(float(state.easiness), 2),
        interval_days=interval_days,
        repetitions=repetitions,
        due_date=due_date,
    )
