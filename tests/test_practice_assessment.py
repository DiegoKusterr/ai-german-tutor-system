"""Conservative practice assessment checks; these do not validate CEFR proficiency."""
import json
from pathlib import Path

import pytest

import learning_app.db as db_module
from learning_app.db import connection_scope, init_db
from learning_app.schemas import SpeakingFeedbackRequest, SpeakingSimulateRequest, WritingGradeRequest, WritingPromptRequest
from learning_app.services.common import ensure_local_user
from learning_app.services.learning import generate_speaking_session, generate_writing_prompt, submit_speaking_turn, submit_writing


A1_TEXT = "Hallo! Ich heiße Lina. Ich lerne Deutsch. Der Kurs ist gut. Ich komme morgen. Vielen Dank!"
B2_TEXT = (
    "Sehr geehrte Damen und Herren, ich besuche Ihren Deutschkurs und möchte eine Lösung für das Problem finden. "
    "Der Unterricht beginnt oft zu spät, und deshalb können wir die Aufgaben nicht gemeinsam besprechen. "
    "Ich schlage einen neuen Termin und eine klare Information für alle Teilnehmer vor. "
    "Außerdem könnten wir die Materialien vor dem Unterricht erhalten, damit wir uns besser vorbereiten. "
    "Bitte bestätigen Sie den Termin und teilen Sie uns mit, welche Lösung möglich ist. "
    "Vielen Dank für Ihre Unterstützung. Mit freundlichen Grüßen, Lina."
)
GOOD_TURNS = [
    "Ich besuche den Deutschkurs und möchte einen anderen Termin vereinbaren. Können wir darüber sprechen?",
    "Wir können den Kurs am Freitag besuchen und zusammen eine Lösung finden. Wäre das möglich?",
    "Ich schlage einen neuen Termin vor, damit alle Teilnehmer kommen können. Können Sie diesen Vorschlag bestätigen?",
]


@pytest.fixture()
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "assessment.db")
    init_db()
    ensure_local_user()


def writing(text: str, level: str = "B2"):
    prompt = generate_writing_prompt(WritingPromptRequest(level=level, topic="Deutschkurs"))
    return submit_writing(WritingGradeRequest(prompt_id=prompt.prompt_id, text=text))


def attempt_row(attempt_id: str):
    with connection_scope() as conn:
        return dict(conn.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,)).fetchone())


def speaking(messages: list[str], level: str = "B2"):
    session = generate_speaking_session(SpeakingSimulateRequest(level=level, topic="Deutschkurs"))
    payload = None
    for message in messages:
        payload = submit_speaking_turn(SpeakingFeedbackRequest(session_id=session.session_id, user_message=message))
    with connection_scope() as conn:
        row = dict(conn.execute("SELECT * FROM attempts WHERE exercise_id = ?", (session.session_id,)).fetchone())
    return row, payload


@pytest.mark.parametrize("text", ["zz "*100, "12345 !? "*30, "!"*40, " "*30, "qwerty "*40])
def test_invalid_writing_cannot_receive_a_passing_score(isolated_db, text):
    result = writing(text)
    assert result.percent == 0
    assert result.total_score == 0
    assert result.what_to_improve
    assert any("heuristisch" in item.comment.lower() for item in result.rubric)


@pytest.mark.parametrize("level,text", [
    ("A1", "Hallo. Ich lerne Deutsch!"),
    ("A1", "Ich komme morgen. Danke!"),
    ("A1", A1_TEXT),
    ("B2", B2_TEXT),
])
def test_meaningful_german_gets_credit_without_being_classed_as_invalid(isolated_db, level, text):
    result = writing(text, level)
    assert result.percent > 15
    assert result.total_score > 0
    assert "heuristisch" in result.official_alignment.lower()
    assert not any("keine auswertbaren" in issue.description.lower() for issue in result.recurring_errors)


def test_repeated_sentences_cannot_game_writing_length(isolated_db):
    repeated = writing("Ich lerne jeden Tag Deutsch. "*20)
    meaningful = writing(B2_TEXT)
    assert repeated.percent <= 30
    assert meaningful.percent > repeated.percent
    assert any("wiederhol" in issue.description.lower() for issue in repeated.recurring_errors)


def test_long_unstructured_word_lists_do_not_earn_high_language_scores(isolated_db):
    text = " ".join("qzx"+str(number)+"uvw" for number in range(100))
    result = writing(text)
    assert result.percent < 60


def test_repeated_function_words_in_a_genuine_beginner_answer_are_allowed(isolated_db):
    text = "Ich lerne Deutsch. Ich arbeite heute. Ich komme morgen. Ich brauche ein Ticket. Ich danke Ihnen."
    assert writing(text, "A1").percent > 30


def test_writing_rubric_percent_and_stored_score_are_consistent(isolated_db):
    result = writing(B2_TEXT)
    row = attempt_row(result.attempt_id)
    assert result.total_score == pytest.approx(sum(item.score for item in result.rubric))
    assert result.percent == round(result.total_score/result.max_score*100, 1)
    assert row["score"] == result.total_score
    assert row["percent"] == result.percent
    feedback = json.loads(row["feedback_json"])
    assert feedback["scoring_version"] == "practice_heuristic_v2"
    assert "heuristisch" in feedback["assessment_note"].lower()


@pytest.mark.parametrize("message", ["zz", "12345 !!!", "qwerty", "  "])
def test_invalid_speaking_has_no_minimum_score_floor(isolated_db, message):
    row, payload = speaking([message]*3)
    assert row["score"] == 0
    assert row["percent"] == 0
    assert payload.is_complete
    assert any("heuristisch" in item.lower() for item in payload.turn_feedback)


@pytest.mark.parametrize("messages", [
    ["Ich lerne Deutsch.", "Ich komme morgen.", "Können Sie mir helfen?"],
    ["Ja.", "Danke!", "Bitte!"],
])
def test_short_meaningful_beginner_speaking_keeps_positive_credit(isolated_db, messages):
    row, payload = speaking(messages, "A1")
    assert row["score"] > 0
    assert not any("keine auswertbaren" in issue.description.lower() for issue in payload.error_tags)


def test_mixed_speaking_assessment_uses_all_learner_turns(isolated_db):
    mixed, _ = speaking(["zz", "zz", GOOD_TURNS[2]])
    good, _ = speaking(GOOD_TURNS)
    assert mixed["percent"] < 60
    assert good["percent"] > mixed["percent"]
    feedback = json.loads(mixed["feedback_json"])
    scores = feedback["turn_scores"]
    assert len(scores) == 3
    assert scores[0]["score"] == 0 and scores[1]["score"] == 0
    assert scores[2]["score"] > 0
    assert mixed["score"] == round(sum(item["score"] for item in scores)/3, 2)
    assert mixed["percent"] == round(mixed["score"]/mixed["max_score"]*100, 1)


def test_earlier_speaking_answers_change_score_with_identical_final_turn(isolated_db):
    mixed, _ = speaking(["zz", "zz", GOOD_TURNS[2]])
    good, _ = speaking(GOOD_TURNS)
    assert mixed["percent"] < good["percent"]


def test_copying_one_answer_into_every_speaking_turn_is_not_high_scoring(isolated_db):
    repeated, _ = speaking([GOOD_TURNS[0]]*3)
    assert repeated["percent"] <= 30
    feedback = json.loads(repeated["feedback_json"])
    assert any("wiederhol" in note.lower() for note in feedback["feedback"])


def test_new_assessments_do_not_rewrite_existing_attempts(isolated_db):
    existing = writing(A1_TEXT, "A1")
    before = attempt_row(existing.attempt_id)
    writing(B2_TEXT)
    speaking(GOOD_TURNS)
    assert attempt_row(existing.attempt_id) == before


def test_genuine_sentences_with_names_do_not_require_function_words(isolated_db):
    text = "Anna arbeitet montags. Peter lernt Deutsch. Marie kauft Brot."
    result = writing(text, "A1")
    assert result.percent > 40
    assert not any("wortliste" in issue.description.lower() for issue in result.recurring_errors)


def test_unique_code_like_word_list_does_not_receive_a_passing_score(isolated_db):
    text = " ".join("qzx"+chr(97+number//26)+chr(97+number%26)+"uvw" for number in range(100))
    assert writing(text).percent < 60


def test_weak_final_turn_preserves_credit_from_earlier_speaking_turns(isolated_db):
    row, _ = speaking([GOOD_TURNS[0], GOOD_TURNS[1], "zz"])
    feedback = json.loads(row["feedback_json"])
    scores = feedback["turn_scores"]
    assert scores[0]["score"] > 0 and scores[1]["score"] > 0
    assert scores[2]["score"] == 0
    assert 0 < row["percent"] < 100
    assert row["score"] == round(sum(item["score"] for item in scores)/3, 2)


def test_session_repetition_cap_is_explicit_in_assessment_metadata(isolated_db):
    row, _ = speaking([GOOD_TURNS[0]]*3)
    feedback = json.loads(row["feedback_json"])
    assert feedback["mean_turn_score"] > feedback["session_score_limit"]
    assert row["score"] == feedback["session_score_limit"]
