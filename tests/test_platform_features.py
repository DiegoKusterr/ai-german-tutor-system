from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import learning_app.db as db_module
import main
from learning_app.db import init_db
from learning_app.schemas import (
    AnalyticsExportDescriptorPayload,
    AppSettingsUpdateRequest,
    CardCreateRequest,
    DeckCreateRequest,
    ExamGenerateRequest,
    GrammarGenerateRequest,
    GrammarSubmitRequest,
    ManualCriterionScoreInput,
    ManualRatingUpsertRequest,
    PlacementStartRequest,
    PlacementSubmitRequest,
    RecommendationFeedbackRequest,
    RecommendationStrategyUpdateRequest,
    ReviewStrategyUpdateRequest,
    ReviewNextRequest,
    RoadmapActivateRequest,
    RoadmapGenerateRequest,
    SpeakingFeedbackRequest,
    SpeakingSimulateRequest,
    WritingGradeRequest,
    WritingPromptRequest,
)
from learning_app.services import (
    create_card,
    create_deck,
    export_experiment_dataset_csv,
    generate_grammar,
    grade_review,
    generate_exam,
    generate_roadmap,
    generate_speaking_session,
    generate_writing_prompt,
    get_experiment_analytics_overview,
    get_recommendation_strategy,
    get_review_strategy,
    get_settings,
    import_starter_deck,
    list_experiment_exports,
    list_manual_ratings,
    list_manual_review_candidates,
    list_manual_rubrics,
    next_review_card,
    start_placement,
    submit_speaking_turn,
    submit_grammar,
    submit_placement,
    submit_writing,
    update_recommendation_strategy,
    update_review_strategy,
    update_settings,
    upsert_manual_rating,
    upsert_recommendation_feedback,
)
from learning_app.services.common import ensure_local_user
from learning_app.services.learning import get_grammar_catalog, get_grammar_theory
from learning_app.services.progress import get_progress_overview
from learning_app.services.exam_mock_llm import choose_exam_mock_ollama_models
from learning_app.services.mock_audio import choose_mock_audio_voice_name, get_mock_audio_provider_preference, resolve_mock_audio_provider
from learning_app.schemas import ReviewGradeRequest


@pytest.fixture()
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "learning_app_platform_test.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    init_db()
    ensure_local_user()
    return db_path


def _manual_scores(sample_type: str, score: float = 4.0) -> list[ManualCriterionScoreInput]:
    rubric = next(item for item in list_manual_rubrics() if item.sample_type == sample_type)
    return [
        ManualCriterionScoreInput(
            criterion_key=criterion.key,
            score=min(score, criterion.max_score),
        )
        for criterion in rubric.criteria
    ]


def test_settings_and_umlaut_roundtrip(isolated_db: Path) -> None:
    settings = get_settings()
    assert settings.interface_language == "de"

    updated = update_settings(
        AppSettingsUpdateRequest(
            interface_language="es",
            explanation_language="de",
            default_goal_exam="goethe_c1",
            default_goal_level="C1",
        )
    )
    assert updated.interface_language == "es"
    assert updated.default_goal_level == "C1"

    deck = create_deck(DeckCreateRequest(name="Umlaute", description="\u00e4 \u00f6 \u00fc \u00df", source="manual"))
    create_card(
        CardCreateRequest(
            deck_id=deck.id,
            card_type="basic",
            front="f\u00fcr die Stra\u00dfe",
            back="for the street",
            extra={"example": "Die Gr\u00fc\u00dfe sind sch\u00f6n."},
            tags=["\u00e4", "\u00f6", "\u00fc", "\u00df"],
        )
    )
    review = next_review_card(ReviewNextRequest(deck_id=deck.id))
    assert review.card is not None
    assert "Stra\u00dfe" in review.card.front
    assert review.card.tags[-1] == "\u00df"


def test_settings_accept_additional_common_languages(isolated_db: Path) -> None:
    updated = update_settings(
        AppSettingsUpdateRequest(
            interface_language="en",
            explanation_language="fr",
            default_goal_exam="goethe_b2",
            default_goal_level="B2",
        )
    )

    assert updated.interface_language == "en"
    assert updated.explanation_language == "fr"


def test_starter_deck_import_and_review_queue(isolated_db: Path) -> None:
    imported = import_starter_deck("irregular_verbs")
    assert imported.imported.imported_cards >= 10
    review = next_review_card(ReviewNextRequest(deck_id=imported.imported.deck.id))
    assert review.card is not None
    assert review.due_count >= 1
    assert review.card.extra.get("example")


def test_placement_and_roadmap_flow(isolated_db: Path) -> None:
    placement = start_placement(PlacementStartRequest(level_hint="B1", goal_exam="goethe_b2"))
    answers = {}
    for item in placement.items:
        answers[item.id] = item.answer if item.item_type != "open" else "Ich lerne Deutsch f\u00fcr Goethe und \u00fcbe jede Woche mit Schreiben, Lesen und Sprechen."
    result = submit_placement(PlacementSubmitRequest(session_id=placement.session_id, answers=answers))
    assert result.overall_level in {"B1", "B2", "C1"}
    assert result.skill_estimates

    roadmap = generate_roadmap(
        RoadmapGenerateRequest(
            placement_session_id=placement.session_id,
            target_level="B2",
            target_exam="goethe_b2",
            weeks=6,
        )
    )
    assert roadmap.weekly_plan
    from learning_app.services.roadmap import activate_roadmap, get_current_roadmap

    active = activate_roadmap(RoadmapActivateRequest(roadmap_id=roadmap.roadmap_id))
    assert active.is_active is True
    assert get_current_roadmap() is not None


def test_grammar_catalog_contains_core_topics(isolated_db: Path) -> None:
    catalog = {item.key for item in get_grammar_catalog()}
    assert "satzbau_verbzweitstellung" in catalog
    assert "adjektivdeklination" in catalog
    assert "konjunktiv_ii" in catalog
    assert "grammatik_gesamtkarte" in catalog
    assert "starke_verben_und_kernverben" in catalog
    assert len(catalog) >= 40


def test_reference_grammar_topics_are_detailed(isolated_db: Path) -> None:
    overview = get_grammar_theory("grammatik_gesamtkarte")
    verbs = get_grammar_theory("starke_verben_und_kernverben")
    assert len(overview.deep_dive) >= 8
    assert len(overview.related_topics) >= 5
    assert any("sein" in entry for entry in verbs.examples)
    assert any("trennbare" in entry.lower() for entry in verbs.deep_dive)


def test_mock_audio_provider_stays_disabled_inside_pytest() -> None:
    assert resolve_mock_audio_provider() == "none"


def test_mock_audio_provider_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOCK_AUDIO_PROVIDER", raising=False)

    assert get_mock_audio_provider_preference() == "none"


def test_mock_audio_voice_selector_prefers_hint_and_gender() -> None:
    voices = ["Microsoft Hedda Desktop", "Microsoft Stefan Desktop", "Microsoft Katja"]

    assert choose_mock_audio_voice_name(voices, hint="Katja", gender="auto") == "Microsoft Katja"
    assert choose_mock_audio_voice_name(voices, hint="", gender="male") == "Microsoft Stefan Desktop"
    assert choose_mock_audio_voice_name(voices, hint="", gender="female") in {"Microsoft Hedda Desktop", "Microsoft Katja"}


def test_exam_mock_model_selection_prefers_fast_installed_models() -> None:
    installed = ["llama3.1:8b", "llama3.2:3b", "llama3.2:1b"]
    selected = choose_exam_mock_ollama_models(installed)

    assert selected[0] == "llama3.2:1b"
    assert "llama3.2:3b" in selected


def test_http_smoke_for_new_endpoints(isolated_db: Path) -> None:
    client = TestClient(main.app)
    assert client.get("/api/settings").status_code == 200
    assert client.get("/api/recommendation/strategy").status_code == 200
    assert client.get("/api/review/strategy").status_code == 200
    assert client.get("/api/validation/rubrics").status_code == 200
    assert client.get("/api/analytics/overview").status_code == 200
    assert client.get("/api/analytics/exports").status_code == 200
    assert client.get("/api/flashcards/starter-decks").status_code == 200
    placement = client.post("/api/placement/start", json={"level_hint": "B1", "goal_exam": "goethe_b2"})
    assert placement.status_code == 200
    placement_payload = placement.json()
    roadmap = client.post("/api/roadmap/generate", json={"current_level": "B1", "target_level": "B2", "target_exam": "goethe_b2", "weeks": 6})
    assert roadmap.status_code == 200
    assert client.post("/api/exam/official", json={"level": "B2", "scope": "module", "module": "lesen"}).status_code == 200
    generate_exam(ExamGenerateRequest(level="B2", scope="module", module="hoeren", variant_seed="http-mock-health"))
    mock_health = client.get("/api/exam/mock-health")
    assert mock_health.status_code == 200
    assert mock_health.json()["recent_runs"]
    assert client.get("/api/exam/mock-media/not-a-valid-key").status_code == 400
    assert placement_payload["session_id"]


def test_recommendation_strategy_can_switch_to_fixed_baseline(isolated_db: Path) -> None:
    initial = get_recommendation_strategy()
    assert initial.active_strategy == "adaptive_heuristic_v1"

    updated = update_recommendation_strategy(RecommendationStrategyUpdateRequest(strategy="fixed_path_v1"))
    assert updated.active_strategy == "fixed_path_v1"

    overview = get_progress_overview("goethe_b2")
    assert overview.recommendation_strategy == "fixed_path_v1"
    assert overview.recommended_exam_scope == "module"
    assert overview.priority_module == "lesen"
    assert overview.next_session is not None
    assert "Vergleichssequenz" in overview.next_session.action or "Vergleichsgruppe" in overview.weekly_plan[0].action


def test_attempts_snapshot_selected_recommendation_strategy(isolated_db: Path) -> None:
    update_recommendation_strategy(RecommendationStrategyUpdateRequest(strategy="fixed_path_v1"))
    placement = start_placement(PlacementStartRequest(level_hint="B1", goal_exam="goethe_b2"))
    answers = {}
    for item in placement.items:
        answers[item.id] = item.answer if item.item_type != "open" else "Ich lerne strukturiert Deutsch und uebe fuer Goethe."
    submit_placement(PlacementSubmitRequest(session_id=placement.session_id, answers=answers))

    with db_module.get_connection() as conn:
        attempt_row = conn.execute(
            """
            SELECT recommendation_strategy
            FROM attempts
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
        event_row = conn.execute(
            """
            SELECT source, strategy_label
            FROM recommendation_events
            WHERE source IN ('strategy_assignment', 'progress_overview', 'roadmap_generate')
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()

    assert attempt_row is not None
    assert attempt_row["recommendation_strategy"] == "fixed_path_v1"
    assert event_row is not None
    assert event_row["strategy_label"] == "fixed_path_v1"


def test_review_strategy_can_switch_to_fixed_interval_baseline(isolated_db: Path) -> None:
    initial = get_review_strategy()
    assert initial.active_strategy == "sm2_v1"

    updated = update_review_strategy(ReviewStrategyUpdateRequest(strategy="fixed_interval_v1"))
    assert updated.active_strategy == "fixed_interval_v1"

    deck = create_deck(DeckCreateRequest(name="Fixed review deck", description="", source="manual"))
    card = create_card(
        CardCreateRequest(
            deck_id=deck.id,
            card_type="basic",
            front="sehen",
            back="to see",
            extra={},
            tags=["verb"],
        )
    )
    payload = grade_review(ReviewGradeRequest(card_id=card.id, quality=4))

    with db_module.get_connection() as conn:
        review_row = conn.execute(
            """
            SELECT review_strategy
            FROM reviews
            ORDER BY reviewed_at DESC
            LIMIT 1
            """
        ).fetchone()

    assert payload.review_strategy == "fixed_interval_v1"
    assert review_row is not None
    assert review_row["review_strategy"] == "fixed_interval_v1"


def test_fixed_interval_baseline_is_less_adaptive_than_sm2(isolated_db: Path) -> None:
    deck = create_deck(DeckCreateRequest(name="Scheduler compare", description="", source="manual"))
    baseline_card = create_card(
        CardCreateRequest(deck_id=deck.id, card_type="basic", front="bleiben", back="to stay", extra={}, tags=["verb"])
    )
    adaptive_card = create_card(
        CardCreateRequest(deck_id=deck.id, card_type="basic", front="bringen", back="to bring", extra={}, tags=["verb"])
    )

    with db_module.get_connection() as conn:
        conn.execute(
            """
            UPDATE cards
            SET easiness = 2.5, interval_days = 6, repetitions = 2, due_date = ?, last_reviewed_at = ?
            WHERE id IN (?, ?)
            """,
            (date.today().isoformat(), date.today().isoformat(), baseline_card.id, adaptive_card.id),
        )

    update_review_strategy(ReviewStrategyUpdateRequest(strategy="fixed_interval_v1"))
    baseline = grade_review(ReviewGradeRequest(card_id=baseline_card.id, quality=5))

    update_review_strategy(ReviewStrategyUpdateRequest(strategy="sm2_v1"))
    adaptive = grade_review(ReviewGradeRequest(card_id=adaptive_card.id, quality=5))

    assert baseline.review_strategy == "fixed_interval_v1"
    assert baseline.interval_days == 7
    assert adaptive.review_strategy == "sm2_v1"
    assert adaptive.interval_days > baseline.interval_days
    assert adaptive.easiness > baseline.easiness


def test_evaluation_strategy_snapshots_are_stored_on_attempts_and_reviews(isolated_db: Path) -> None:
    placement = start_placement(PlacementStartRequest(level_hint="B1", goal_exam="goethe_b2"))
    answers = {}
    for item in placement.items:
        answers[item.id] = item.answer if item.item_type != "open" else "Ich lerne jeden Tag Deutsch und uebe gezielt fuer Goethe."
    submit_placement(PlacementSubmitRequest(session_id=placement.session_id, answers=answers))

    deck = create_deck(DeckCreateRequest(name="Eval deck", description="", source="manual"))
    card = create_card(
        CardCreateRequest(
            deck_id=deck.id,
            card_type="basic",
            front="gehen",
            back="to go",
            extra={},
            tags=["verb"],
        )
    )
    grade_review(ReviewGradeRequest(card_id=card.id, quality=4))

    with db_module.get_connection() as conn:
        attempt_row = conn.execute(
            """
            SELECT recommendation_strategy, review_strategy, assessment_mode
            FROM attempts
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
        review_row = conn.execute(
            """
            SELECT review_strategy
            FROM reviews
            ORDER BY reviewed_at DESC
            LIMIT 1
            """
        ).fetchone()

    assert attempt_row is not None
    assert attempt_row["recommendation_strategy"] == "adaptive_heuristic_v1"
    assert attempt_row["review_strategy"] == "sm2_v1"
    assert attempt_row["assessment_mode"] == "standard_v1"
    assert review_row is not None
    assert review_row["review_strategy"] == "sm2_v1"


def test_review_exports_capture_retention_signals(isolated_db: Path) -> None:
    deck = create_deck(DeckCreateRequest(name="Retention deck", description="", source="manual"))
    card = create_card(
        CardCreateRequest(deck_id=deck.id, card_type="basic", front="entscheiden", back="to decide", extra={}, tags=["verb"])
    )

    with db_module.get_connection() as conn:
        conn.execute(
            """
            UPDATE cards
            SET easiness = 2.5, interval_days = 3, repetitions = 2, due_date = ?, last_reviewed_at = ?
            WHERE id = ?
            """,
            ((date.today() - timedelta(days=2)).isoformat(), (date.today() - timedelta(days=5)).isoformat(), card.id),
        )

    payload = grade_review(ReviewGradeRequest(card_id=card.id, quality=4))

    with db_module.get_connection() as conn:
        export_row = conn.execute(
            """
            SELECT review_strategy, previous_interval_days, days_since_last_review, days_overdue, successful_recall
            FROM experiment_reviews_export
            ORDER BY reviewed_at DESC
            LIMIT 1
            """
        ).fetchone()

    assert payload.successful_recall is True
    assert payload.days_since_last_review == 5
    assert payload.days_overdue == 2
    assert export_row is not None
    assert export_row["review_strategy"] == "sm2_v1"
    assert export_row["previous_interval_days"] == 3
    assert export_row["days_since_last_review"] == 5
    assert export_row["days_overdue"] == 2
    assert int(export_row["successful_recall"]) == 1


def test_recommendation_events_and_export_views_are_populated(isolated_db: Path) -> None:
    generate_roadmap(
        RoadmapGenerateRequest(
            current_level="B1",
            target_level="B2",
            target_exam="goethe_b2",
            weeks=6,
        )
    )
    overview = get_progress_overview("goethe_b2")
    assert overview.current_goal == "goethe_b2"

    with db_module.get_connection() as conn:
        event_rows = conn.execute(
            """
            SELECT source, strategy_label, goal_exam
            FROM recommendation_events
            ORDER BY created_at ASC
            """
        ).fetchall()
        view_names = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'view' AND name LIKE 'experiment_%'"
            ).fetchall()
        }
        export_row = conn.execute(
            """
            SELECT source, recommendation_strategy, goal_exam
            FROM experiment_recommendations_export
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()

    assert len(event_rows) >= 2
    assert {row["source"] for row in event_rows} >= {"roadmap_generate", "progress_overview"}
    assert all(row["strategy_label"] == "adaptive_heuristic_v1" for row in event_rows)
    assert view_names >= {
        "experiment_attempts_export",
        "experiment_reviews_export",
        "experiment_recommendations_export",
    }
    assert export_row is not None
    assert export_row["goal_exam"] == "goethe_b2"


def test_grammar_attempt_can_link_to_specific_recommendation_event(isolated_db: Path) -> None:
    overview = get_progress_overview("goethe_b2")
    assert overview.recommendation_event_id

    grammar = generate_grammar(
        GrammarGenerateRequest(
            level="B2",
            focus="satzbau_verbzweitstellung",
            recommendation_event_id=overview.recommendation_event_id,
        )
    )
    answers = {item.id: item.answer for item in grammar.items}
    submit_grammar(GrammarSubmitRequest(exercise_id=grammar.exercise_id, answers=answers))

    with db_module.get_connection() as conn:
        attempt_row = conn.execute(
            """
            SELECT launched_from_recommendation, recommendation_event_id, linked_recommendation_strategy
            FROM attempts
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
        export_row = conn.execute(
            """
            SELECT launched_from_recommendation, recommendation_event_id, linked_recommendation_source
            FROM experiment_attempts_export
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()

    assert attempt_row is not None
    assert int(attempt_row["launched_from_recommendation"]) == 1
    assert attempt_row["recommendation_event_id"] == overview.recommendation_event_id
    assert attempt_row["linked_recommendation_strategy"] == "adaptive_heuristic_v1"
    assert export_row is not None
    assert int(export_row["launched_from_recommendation"]) == 1
    assert export_row["linked_recommendation_source"] == "progress_overview"


def test_review_grade_can_link_to_specific_recommendation_event(isolated_db: Path) -> None:
    overview = get_progress_overview("goethe_b2")
    assert overview.recommendation_event_id

    deck = create_deck(DeckCreateRequest(name="Reco review deck", description="", source="manual"))
    card = create_card(
        CardCreateRequest(
            deck_id=deck.id,
            card_type="basic",
            front="bleiben",
            back="to stay",
            extra={},
            tags=["verb"],
        )
    )

    next_payload = next_review_card(ReviewNextRequest(deck_id=deck.id, recommendation_event_id=overview.recommendation_event_id))
    assert next_payload.card is not None
    assert next_payload.recommendation_event_id == overview.recommendation_event_id

    grade_review(
        ReviewGradeRequest(
            card_id=card.id,
            quality=4,
            recommendation_event_id=next_payload.recommendation_event_id,
        )
    )

    with db_module.get_connection() as conn:
        review_row = conn.execute(
            """
            SELECT launched_from_recommendation, recommendation_event_id, linked_recommendation_strategy
            FROM reviews
            ORDER BY reviewed_at DESC
            LIMIT 1
            """
        ).fetchone()
        export_row = conn.execute(
            """
            SELECT launched_from_recommendation, recommendation_event_id, linked_recommendation_source
            FROM experiment_reviews_export
            ORDER BY reviewed_at DESC
            LIMIT 1
            """
        ).fetchone()

    assert review_row is not None
    assert int(review_row["launched_from_recommendation"]) == 1
    assert review_row["recommendation_event_id"] == overview.recommendation_event_id
    assert review_row["linked_recommendation_strategy"] == "adaptive_heuristic_v1"
    assert export_row is not None
    assert int(export_row["launched_from_recommendation"]) == 1
    assert export_row["linked_recommendation_source"] == "progress_overview"


def test_manual_validation_can_rate_writing_attempt_and_export_dataset(isolated_db: Path) -> None:
    rubrics = {item.sample_type: item for item in list_manual_rubrics()}
    assert "not an official Goethe scoring procedure" in rubrics["writing"].note

    prompt = generate_writing_prompt(
        WritingPromptRequest(
            level="B2",
            text_type="opinion",
            topic="Homeoffice und Teamarbeit",
        )
    )
    submitted_text = (
        "Meiner Meinung nach ist Homeoffice fuer viele Teams sinnvoll, wenn klare Regeln gelten. "
        "Man spart Zeit auf dem Weg zur Arbeit, aber die Kommunikation muss bewusst organisiert werden. "
        "Deshalb sollte jedes Team feste Online-Termine und klare Aufgaben haben."
    )
    grade = submit_writing(WritingGradeRequest(prompt_id=prompt.prompt_id, text=submitted_text))

    candidates = list_manual_review_candidates(sample_type="writing", reviewer_id="rater_a")
    candidate = next(item for item in candidates if item.attempt_id == grade.attempt_id)
    assert submitted_text[:40] in candidate.artifact_text
    assert candidate.assessment_mode == "standard_v1"

    rating = upsert_manual_rating(
        ManualRatingUpsertRequest(
            attempt_id=grade.attempt_id,
            reviewer_id="rater_a",
            reviewer_name="Reviewer A",
            criteria=_manual_scores("writing", score=4.0),
            notes="Solide Antwort mit klarer Struktur, aber begrenzter sprachlicher Variation.",
        )
    )
    updated = upsert_manual_rating(
        ManualRatingUpsertRequest(
            attempt_id=grade.attempt_id,
            reviewer_id="rater_a",
            reviewer_name="Reviewer A",
            criteria=_manual_scores("writing", score=4.5),
            notes="Aktualisierte Bewertung nach zweiter Durchsicht.",
        )
    )
    ratings = list_manual_ratings(grade.attempt_id)

    with db_module.get_connection() as conn:
        export_row = conn.execute(
            """
            SELECT sample_type, manual_score, automated_score, user_answers_json, prompt_json
            FROM manual_validation_export
            WHERE attempt_id = ?
            """,
            (grade.attempt_id,),
        ).fetchone()

    assert rating.rating_id == updated.rating_id
    assert len(ratings) == 1
    assert ratings[0].overall_score == updated.overall_score
    assert export_row is not None
    assert export_row["sample_type"] == "writing"
    assert submitted_text[:40] in export_row["user_answers_json"]
    assert prompt.title in export_row["prompt_json"]


def test_manual_validation_speaking_candidates_include_full_transcript(isolated_db: Path) -> None:
    rubrics = {item.sample_type: item for item in list_manual_rubrics()}
    assert "does not claim official oral-exam validity" in rubrics["speaking"].note

    session = generate_speaking_session(
        SpeakingSimulateRequest(
            level="B2",
            mode="goethe_sprechen",
            topic="Nachhaltige Mobilitaet in der Stadt",
        )
    )
    turns = [
        "Ich finde nachhaltige Mobilitaet wichtig, weil viele Menschen jeden Tag im Stau stehen und die Luft schlechter wird.",
        "Ein konkreter Vorschlag waere ein guenstiges Monatsticket, damit mehr Berufstaetige Bus und Bahn regelmaessig nutzen.",
        "Wir koennten ausserdem sichere Fahrradwege planen und Firmen einbeziehen, damit weniger Autos noetig sind. Was meinen Sie dazu?",
    ]
    final_payload = None
    for turn in turns:
        final_payload = submit_speaking_turn(
            SpeakingFeedbackRequest(
                session_id=session.session_id,
                user_message=turn,
            )
        )

    assert final_payload is not None
    assert final_payload.is_complete is True

    candidates = list_manual_review_candidates(sample_type="speaking", reviewer_id="rater_b")
    candidate = next(item for item in candidates if item.title == session.title)
    assert turns[0] in candidate.artifact_text
    assert turns[1] in candidate.artifact_text
    assert turns[2] in candidate.artifact_text

    rating = upsert_manual_rating(
        ManualRatingUpsertRequest(
            attempt_id=candidate.attempt_id,
            reviewer_id="rater_b",
            reviewer_name="Reviewer B",
            criteria=_manual_scores("speaking", score=3.5),
            notes="Nur transcriptbasiert bewertet; Aussprache und Fluessigkeit sind nicht voll sichtbar.",
        )
    )

    with db_module.get_connection() as conn:
        export_row = conn.execute(
            """
            SELECT sample_type, user_answers_json, corrected_json
            FROM manual_validation_export
            WHERE attempt_id = ?
            """,
            (candidate.attempt_id,),
        ).fetchone()

    assert rating.sample_type == "speaking"
    assert export_row is not None
    assert export_row["sample_type"] == "speaking"
    assert "\"transcript\"" in export_row["user_answers_json"]
    assert turns[0] in export_row["user_answers_json"]


def test_experiment_analytics_overview_and_exports_support_thesis_results(isolated_db: Path) -> None:
    client = TestClient(main.app)

    adaptive_overview = get_progress_overview("goethe_b2")
    assert adaptive_overview.recommendation_event_id

    feedback_response = client.post(
        "/api/analytics/recommendation-feedback",
        json={
            "recommendation_event_id": adaptive_overview.recommendation_event_id,
            "usefulness_score": 5,
            "notes": "Helpful next step for focused grammar practice.",
        },
    )
    assert feedback_response.status_code == 200

    adaptive_grammar = generate_grammar(
        GrammarGenerateRequest(
            level="B2",
            focus="satzbau_verbzweitstellung",
            recommendation_event_id=adaptive_overview.recommendation_event_id,
        )
    )
    submit_grammar(
        GrammarSubmitRequest(
            exercise_id=adaptive_grammar.exercise_id,
            answers={item.id: "" for item in adaptive_grammar.items},
        )
    )

    update_recommendation_strategy(RecommendationStrategyUpdateRequest(strategy="fixed_path_v1"))
    fixed_overview = get_progress_overview("goethe_b2")
    assert fixed_overview.recommendation_event_id

    fixed_grammar = generate_grammar(
        GrammarGenerateRequest(
            level="B2",
            focus="adjektivdeklination",
            recommendation_event_id=fixed_overview.recommendation_event_id,
        )
    )
    submit_grammar(
        GrammarSubmitRequest(
            exercise_id=fixed_grammar.exercise_id,
            answers={item.id: item.answer for item in fixed_grammar.items},
        )
    )

    deck = create_deck(DeckCreateRequest(name="Analytics deck", description="", source="manual"))
    fixed_review_card = create_card(
        CardCreateRequest(deck_id=deck.id, card_type="basic", front="anfangen", back="to begin", extra={}, tags=["verb"])
    )
    adaptive_review_card = create_card(
        CardCreateRequest(deck_id=deck.id, card_type="basic", front="vermeiden", back="to avoid", extra={}, tags=["verb"])
    )
    update_review_strategy(ReviewStrategyUpdateRequest(strategy="fixed_interval_v1"))
    grade_review(ReviewGradeRequest(card_id=fixed_review_card.id, quality=3))
    update_review_strategy(ReviewStrategyUpdateRequest(strategy="sm2_v1"))
    grade_review(ReviewGradeRequest(card_id=adaptive_review_card.id, quality=5))

    prompt = generate_writing_prompt(
        WritingPromptRequest(
            level="B2",
            text_type="complaint",
            topic="Verspaetete Lieferung",
        )
    )
    writing_grade = submit_writing(
        WritingGradeRequest(
            prompt_id=prompt.prompt_id,
            text=(
                "Sehr geehrte Damen und Herren, meine Bestellung ist noch nicht angekommen. "
                "Ich habe schon mehr als eine Woche gewartet und brauche die Lieferung dringend. "
                "Bitte pruefen Sie den Status und informieren Sie mich schnell ueber die naechsten Schritte."
            ),
        )
    )
    upsert_manual_rating(
        ManualRatingUpsertRequest(
            attempt_id=writing_grade.attempt_id,
            reviewer_id="thesis_rater",
            reviewer_name="Thesis Rater",
            criteria=_manual_scores("writing", score=4.0),
            notes="Manual validation sample for analytics summary.",
        )
    )

    analytics = get_experiment_analytics_overview()
    exports = {item.key: item for item in list_experiment_exports()}
    csv_payload, filename = export_experiment_dataset_csv("recommendation_summary")
    csv_response = client.get("/api/analytics/exports/recommendation_summary?format=csv")

    assert "attempt_strategy_summary" in exports
    assert exports["recommendation_feedback"].row_count >= 1
    assert exports["manual_agreement"].row_count >= 1
    assert any(item.recommendation_strategy == "adaptive_heuristic_v1" for item in analytics.attempt_strategy_summaries)
    assert any(item.recommendation_strategy == "fixed_path_v1" for item in analytics.attempt_strategy_summaries)
    assert analytics.progress_daily
    assert analytics.error_summaries
    assert any(item.review_strategy == "fixed_interval_v1" for item in analytics.review_strategy_summaries)
    assert any(item.review_strategy == "sm2_v1" for item in analytics.review_strategy_summaries)
    assert any(item.usefulness_responses >= 1 for item in analytics.recommendation_summaries)
    assert any(item.sample_type == "writing" for item in analytics.manual_agreement_summaries)
    assert filename == "experiment_recommendation_summary.csv"
    assert "recommendation_strategy" in csv_payload.splitlines()[0]
    assert csv_response.status_code == 200
    assert "text/csv" in csv_response.headers["content-type"]
    assert "recommendation_strategy" in csv_response.text.splitlines()[0]
