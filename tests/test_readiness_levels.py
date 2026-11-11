"""Target-level readiness uses exam evidence without erasing general activity."""
from datetime import date, timedelta
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
import learning_app.db as db_module
from learning_app.db import connection_scope, init_db
from learning_app.schemas import PlacementStartRequest, PlacementSubmitRequest, ProgressOverviewPayload
from learning_app.services.common import ensure_local_user, make_id, save_attempt, save_exercise
from learning_app.services.placement import start_placement, submit_placement
from learning_app.services.progress import get_progress_overview, list_exam_history


@pytest.fixture()
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "readiness.db")
    init_db()
    ensure_local_user()


def add_exam(level: str, module: str, percent: float, day: date | None = None) -> str:
    exercise_id = make_id("fictional_exam")
    save_exercise(
        exercise_id=exercise_id, category="exam", module=module, level=level,
        title="Fictional examination", prompt_payload={}, answer_payload={},
        criteria_payload=[], meta_payload={},
    )
    attempt_id = save_attempt(
        exercise_id=exercise_id, category="exam", module=module, level=level,
        user_answers={}, score=percent, max_score=100, percent=percent,
        feedback_payload={}, corrected_payload={}, error_tags_payload=[],
    )
    if day is not None:
        with connection_scope() as conn:
            conn.execute("UPDATE attempts SET created_at = ? WHERE id = ?", (day.isoformat()+"T12:00:00Z", attempt_id))
    return attempt_id


def attempts_snapshot() -> list[tuple]:
    with connection_scope() as conn:
        return [tuple(row) for row in conn.execute("SELECT * FROM attempts ORDER BY id")]


def module_stat(overview, module: str):
    return next(item for item in overview.module_probabilities if item.module == module)


@pytest.mark.parametrize("target,other", [("B2", "A1"), ("A1", "B2")])
def test_other_level_exams_do_not_supply_readiness_but_remain_in_history(isolated_db, target, other):
    add_exam(other, "lesen", 100)
    add_exam(other, "full", 100)
    before = attempts_snapshot()
    overview = get_progress_overview("goethe_"+target.lower())
    assert overview.full_exam_probability.probability_percent is None
    assert all(item.attempts == 0 and item.probability_percent is None for item in overview.module_probabilities)
    assert overview.priority_module is None
    assert overview.streak_days == 1
    assert {item.level for item in list_exam_history()} == {other}
    assert len(list_exam_history()) == 2
    assert attempts_snapshot() == before


def test_mixed_levels_and_goal_changes_keep_independent_exam_results(isolated_db):
    add_exam("A1", "lesen", 100)
    add_exam("A1", "full", 100)
    add_exam("B2", "lesen", 40)
    add_exam("B2", "full", 50)
    before = attempts_snapshot()
    first_b2 = get_progress_overview("goethe_b2")
    a1 = get_progress_overview("goethe_a1")
    second_b2 = get_progress_overview("goethe_b2")
    assert module_stat(first_b2, "lesen").average_percent == 40
    assert module_stat(first_b2, "lesen").attempts == 1
    assert first_b2.full_exam_probability.average_percent == 50
    assert first_b2.full_exam_probability.attempts == 1
    assert module_stat(a1, "lesen").average_percent == 100
    assert a1.full_exam_probability.average_percent == 100
    assert second_b2.module_probabilities == first_b2.module_probabilities
    assert second_b2.full_exam_probability == first_b2.full_exam_probability
    with connection_scope() as conn:
        context = json.loads(conn.execute(
            "SELECT context_json FROM recommendation_events WHERE id = ?", (first_b2.recommendation_event_id,)
        ).fetchone()[0])
    assert context["exam_attempts"] == 2
    assert context["exam_average"] == 45
    assert attempts_snapshot() == before


def test_partial_target_module_evidence_is_labelled_as_an_estimate(isolated_db):
    add_exam("A1", "lesen", 100)
    add_exam("B2", "lesen", 70)
    add_exam("B2", "hoeren", 30)
    overview = get_progress_overview("goethe_b2")
    assert module_stat(overview, "lesen").average_percent == 70
    assert module_stat(overview, "hoeren").average_percent == 30
    assert module_stat(overview, "schreiben").probability_percent is None
    assert overview.full_exam_probability.attempts == 0
    assert overview.full_exam_probability.basis == "geschaetzt"
    assert overview.full_exam_probability.average_percent == 44
    assert "2/4" in overview.full_exam_probability.note
    assert overview.priority_module == "hoeren"


def test_no_exam_data_returns_compatible_empty_indicators(isolated_db):
    client = TestClient(main.app)
    response = client.get("/api/progress/overview?goal=goethe_b2")
    assert response.status_code == 200
    overview = ProgressOverviewPayload.model_validate(response.json())
    assert overview.full_exam_probability.basis == "keine_daten"
    assert overview.full_exam_probability.probability_percent is None
    assert len(overview.module_probabilities) == 4
    assert overview.streak_days == 0
    assert overview.recommended_exam_scope == "full"
    client.close()


def test_placement_is_visible_but_is_not_exam_readiness_evidence(isolated_db):
    session = start_placement(PlacementStartRequest(goal_exam="goethe_b2"))
    result = submit_placement(PlacementSubmitRequest(
        session_id=session.session_id, answers={item.id: item.answer for item in session.items},
    ))
    overview = get_progress_overview("goethe_b2")
    assert overview.latest_placement_level == result.overall_level
    assert overview.full_exam_probability.probability_percent is None
    assert all(item.probability_percent is None for item in overview.module_probabilities)


def test_streak_and_history_preserve_activity_from_all_levels(isolated_db):
    today = date.today()
    add_exam("A1", "lesen", 90, today)
    add_exam("B2", "full", 50, today-timedelta(days=1))
    add_exam("A1", "full", 80, today-timedelta(days=2))
    before = attempts_snapshot()
    assert get_progress_overview("goethe_b2").streak_days == 3
    assert get_progress_overview("goethe_a1").streak_days == 3
    assert len(list_exam_history()) == 3
    assert attempts_snapshot() == before


def test_indicators_disclose_heuristic_status_even_with_multiple_exams(isolated_db):
    add_exam("B2", "lesen", 80)
    add_exam("B2", "lesen", 85)
    overview = get_progress_overview("goethe_b2")
    stat = module_stat(overview, "lesen")
    assert stat.basis == "empirisch"
    assert "heuristisch" in stat.note.lower()
    assert "keine validierte" in stat.note.lower()
    assert "heuristisch" in overview.exam_readiness.lower()
