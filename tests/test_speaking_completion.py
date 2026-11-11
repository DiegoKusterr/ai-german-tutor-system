"""Completed speaking sessions must reject retries without changing stored data."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import learning_app.db as db_module
import main
from learning_app.db import connection_scope, init_db
from learning_app.schemas import SpeakingFeedbackRequest, SpeakingSimulateRequest
from learning_app.services.learning import generate_speaking_session, submit_speaking_turn


MESSAGES = [
    "Wir planen eine erfundene Lesung und bestellen dafür einige blaue Notizbücher.",
    "Die Lieferung soll am Freitag kommen, weil die fiktive Veranstaltung dann beginnt.",
    "Wir möchten den Termin bestätigen und die Menge prüfen. Können Sie das bestätigen?",
]


@pytest.fixture()
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "speaking-completion.db"
    monkeypatch.setattr(db_module, "DB_PATH", path)
    init_db()
    return path


def database_snapshot() -> str:
    with connection_scope() as connection:
        return "\n".join(connection.iterdump())


def test_completed_session_returns_409_on_repeated_submissions_without_writes(isolated_db: Path) -> None:
    client = TestClient(main.app, raise_server_exceptions=False)
    response = client.post("/api/speaking/simulate", json={
        "level": "B2", "mode": "goethe_sprechen", "topic": "fictional bookshop",
    })
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    for number, message in enumerate(MESSAGES, 1):
        response = client.post("/api/speaking/feedback", json={
            "session_id": session_id, "user_message": message,
        })
        assert response.status_code == 200
        assert response.json()["turn_number"] == number
        assert response.json()["is_complete"] is (number == 3)
    with connection_scope() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM attempts WHERE exercise_id = ?", (session_id,)
        ).fetchone()[0] == 1
    before = database_snapshot()
    for _ in range(2):
        response = client.post("/api/speaking/feedback", json={
            "session_id": session_id, "user_message": "Noch eine erfundene Antwort.",
        })
        assert response.status_code == 409
        assert response.json()["detail"] == "Sprechsitzung ist bereits abgeschlossen."
        assert database_snapshot() == before
    client.close()


def test_completed_session_service_rejects_without_changing_database(isolated_db: Path) -> None:
    session = generate_speaking_session(SpeakingSimulateRequest(level="B2", mode="goethe_sprechen"))
    for message in MESSAGES:
        submit_speaking_turn(SpeakingFeedbackRequest(session_id=session.session_id, user_message=message))
    before = database_snapshot()
    with pytest.raises(ValueError, match="bereits abgeschlossen"):
        submit_speaking_turn(SpeakingFeedbackRequest(
            session_id=session.session_id, user_message="Ein weiterer fiktiver Beitrag.",
        ))
    assert database_snapshot() == before


def test_missing_speaking_session_keeps_404_and_does_not_write(isolated_db: Path) -> None:
    before = database_snapshot()
    client = TestClient(main.app, raise_server_exceptions=False)
    response = client.post("/api/speaking/feedback", json={
        "session_id": "fictional-missing-session", "user_message": "Eine erfundene Antwort.",
    })
    assert response.status_code == 404
    assert database_snapshot() == before
    client.close()
