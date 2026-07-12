from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse

from .schemas import (
    AnalyticsExportDescriptorPayload,
    AppSettingsPayload,
    AppSettingsUpdateRequest,
    CardCreateRequest,
    CardPayload,
    CardUpdateRequest,
    DeckCreateRequest,
    DeckDetailPayload,
    DeckPayload,
    DeckUpdateRequest,
    EvaluationPayload,
    ExamGenerateRequest,
    ExamPayload,
    ExamSubmitRequest,
    ExperimentAnalyticsOverviewPayload,
    FlashcardImportPayload,
    FlashcardImportRequest,
    GrammarGenerateRequest,
    GrammarPayload,
    GrammarSubmitRequest,
    GrammarTheoryPayload,
    GrammarTopicSummary,
    MockGenerationHealthPayload,
    ManualRatingPayload,
    ManualRatingUpsertRequest,
    ManualReviewCandidatePayload,
    ManualRubricDefinition,
    OfficialExamPayload,
    OfficialExamRequest,
    PlacementHistoryItem,
    PlacementResultPayload,
    PlacementStartPayload,
    PlacementStartRequest,
    PlacementSubmitRequest,
    ProgressOverviewPayload,
    RecommendationFeedbackPayload,
    RecommendationFeedbackRequest,
    RecommendationStrategyPayload,
    RecommendationStrategyUpdateRequest,
    ReviewStrategyPayload,
    ReviewStrategyUpdateRequest,
    ReviewGradePayload,
    ReviewGradeRequest,
    ReviewNextPayload,
    ReviewNextRequest,
    RoadmapActivateRequest,
    RoadmapPayload,
    RoadmapGenerateRequest,
    SpeakingFeedbackRequest,
    SpeakingSimulationPayload,
    SpeakingSimulateRequest,
    SpeakingTurnPayload,
    StarterDeckImportPayload,
    StarterDeckSummary,
    VocabFromTopicRequest,
    VocabPayload,
    WritingGradePayload,
    WritingGradeRequest,
    WritingPromptPayload,
    WritingPromptRequest,
)
from .services import (
    activate_roadmap,
    create_card,
    create_deck,
    delete_card,
    delete_deck,
    export_experiment_dataset_csv,
    generate_exam,
    generate_grammar,
    generate_roadmap,
    generate_speaking_session,
    generate_vocab,
    get_mock_audio_file,
    generate_writing_prompt,
    get_current_roadmap,
    get_deck_detail,
    get_experiment_analytics_overview,
    get_mock_generation_health,
    get_official_exam,
    get_official_resource,
    get_grammar_catalog,
    get_grammar_theory,
    get_progress_overview,
    get_recommendation_strategy,
    get_review_strategy,
    get_settings,
    get_top_mistakes,
    grade_review,
    import_flashcards,
    import_starter_deck,
    list_decks,
    list_exam_history,
    list_experiment_exports,
    list_manual_ratings,
    list_manual_review_candidates,
    list_manual_rubrics,
    list_placement_history,
    list_starter_decks,
    next_review_card,
    start_placement,
    submit_exam,
    submit_grammar,
    submit_placement,
    submit_speaking_turn,
    submit_writing,
    update_card,
    update_deck,
    update_recommendation_strategy,
    update_review_strategy,
    update_settings,
    upsert_manual_rating,
    upsert_recommendation_feedback,
)

router = APIRouter(prefix="/api", tags=["learning-platform"])


@router.get("/settings", response_model=AppSettingsPayload)
def settings_get() -> AppSettingsPayload:
    return get_settings()


@router.put("/settings", response_model=AppSettingsPayload)
def settings_put(req: AppSettingsUpdateRequest) -> AppSettingsPayload:
    return update_settings(req)


@router.get("/recommendation/strategy", response_model=RecommendationStrategyPayload)
def recommendation_strategy_get() -> RecommendationStrategyPayload:
    return get_recommendation_strategy()


@router.put("/recommendation/strategy", response_model=RecommendationStrategyPayload)
def recommendation_strategy_put(req: RecommendationStrategyUpdateRequest) -> RecommendationStrategyPayload:
    return update_recommendation_strategy(req)


@router.get("/review/strategy", response_model=ReviewStrategyPayload)
def review_strategy_get() -> ReviewStrategyPayload:
    return get_review_strategy()


@router.put("/review/strategy", response_model=ReviewStrategyPayload)
def review_strategy_put(req: ReviewStrategyUpdateRequest) -> ReviewStrategyPayload:
    return update_review_strategy(req)


@router.post("/exam/official", response_model=OfficialExamPayload)
def exam_official(req: OfficialExamRequest) -> OfficialExamPayload:
    return get_official_exam(req)


@router.post("/exam/generate", response_model=ExamPayload)
def exam_generate(req: ExamGenerateRequest) -> ExamPayload:
    return generate_exam(req)


@router.post("/exam/submit", response_model=EvaluationPayload)
def exam_submit(req: ExamSubmitRequest) -> EvaluationPayload:
    try:
        return submit_exam(req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/exam/resource")
def exam_resource(url: str = Query(..., min_length=12)) -> Response:
    try:
        payload, content_type = get_official_resource(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=payload,
        media_type=content_type,
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/exam/mock-media/{audio_key}")
def exam_mock_media(audio_key: str) -> FileResponse:
    try:
        path, media_type, filename = get_mock_audio_file(audio_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/exam/history")
def exam_history() -> list:
    return list_exam_history()


@router.get("/exam/mock-health", response_model=MockGenerationHealthPayload)
def exam_mock_health() -> MockGenerationHealthPayload:
    return get_mock_generation_health()


@router.post("/placement/start", response_model=PlacementStartPayload)
def placement_start(req: PlacementStartRequest) -> PlacementStartPayload:
    return start_placement(req)


@router.post("/placement/submit", response_model=PlacementResultPayload)
def placement_submit(req: PlacementSubmitRequest) -> PlacementResultPayload:
    try:
        return submit_placement(req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/placement/history", response_model=list[PlacementHistoryItem])
def placement_history() -> list[PlacementHistoryItem]:
    return list_placement_history()


@router.post("/roadmap/generate", response_model=RoadmapPayload)
def roadmap_generate(req: RoadmapGenerateRequest) -> RoadmapPayload:
    return generate_roadmap(req)


@router.get("/roadmap/current", response_model=RoadmapPayload | None)
def roadmap_current() -> RoadmapPayload | None:
    return get_current_roadmap()


@router.post("/roadmap/activate", response_model=RoadmapPayload)
def roadmap_activate(req: RoadmapActivateRequest) -> RoadmapPayload:
    try:
        return activate_roadmap(req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/grammar/generate", response_model=GrammarPayload)
def grammar_generate(req: GrammarGenerateRequest) -> GrammarPayload:
    return generate_grammar(req)


@router.get("/grammar/catalog", response_model=list[GrammarTopicSummary])
def grammar_catalog() -> list[GrammarTopicSummary]:
    return get_grammar_catalog()


@router.get("/grammar/theory/{topic_key}", response_model=GrammarTheoryPayload)
def grammar_theory(topic_key: str) -> GrammarTheoryPayload:
    try:
        return get_grammar_theory(topic_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/grammar/submit", response_model=EvaluationPayload)
def grammar_submit(req: GrammarSubmitRequest) -> EvaluationPayload:
    try:
        return submit_grammar(req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/writing/prompt", response_model=WritingPromptPayload)
def writing_prompt(req: WritingPromptRequest) -> WritingPromptPayload:
    return generate_writing_prompt(req)


@router.post("/writing/grade", response_model=WritingGradePayload)
def writing_grade(req: WritingGradeRequest) -> WritingGradePayload:
    try:
        return submit_writing(req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/speaking/simulate", response_model=SpeakingSimulationPayload)
def speaking_simulate(req: SpeakingSimulateRequest) -> SpeakingSimulationPayload:
    return generate_speaking_session(req)


@router.post("/speaking/feedback", response_model=SpeakingTurnPayload)
def speaking_feedback(req: SpeakingFeedbackRequest) -> SpeakingTurnPayload:
    try:
        return submit_speaking_turn(req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/vocab/from-topic", response_model=VocabPayload)
def vocab_from_topic(req: VocabFromTopicRequest) -> VocabPayload:
    return generate_vocab(req)


@router.get("/flashcards/starter-decks", response_model=list[StarterDeckSummary])
def starter_decks() -> list[StarterDeckSummary]:
    return list_starter_decks()


@router.post("/flashcards/starter-decks/{deck_key}/import", response_model=StarterDeckImportPayload)
def starter_decks_import(deck_key: str) -> StarterDeckImportPayload:
    try:
        return import_starter_deck(deck_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/flashcards/decks", response_model=list[DeckPayload])
def flashcards_decks() -> list[DeckPayload]:
    return list_decks()


@router.get("/validation/rubrics", response_model=list[ManualRubricDefinition])
def validation_rubrics() -> list[ManualRubricDefinition]:
    return list_manual_rubrics()


@router.get("/validation/candidates", response_model=list[ManualReviewCandidatePayload])
def validation_candidates(
    sample_type: str,
    limit: int = 20,
    reviewer_id: str | None = None,
    only_unrated: bool = True,
) -> list[ManualReviewCandidatePayload]:
    if sample_type not in {"writing", "speaking"}:
        raise HTTPException(status_code=400, detail="sample_type must be 'writing' or 'speaking'.")
    return list_manual_review_candidates(
        sample_type=sample_type,
        limit=limit,
        reviewer_id=reviewer_id,
        only_unrated=only_unrated,
    )


@router.get("/validation/attempts/{attempt_id}/ratings", response_model=list[ManualRatingPayload])
def validation_attempt_ratings(attempt_id: str) -> list[ManualRatingPayload]:
    return list_manual_ratings(attempt_id)


@router.post("/validation/ratings", response_model=ManualRatingPayload)
def validation_rating_upsert(req: ManualRatingUpsertRequest) -> ManualRatingPayload:
    try:
        return upsert_manual_rating(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analytics/overview", response_model=ExperimentAnalyticsOverviewPayload)
def analytics_overview() -> ExperimentAnalyticsOverviewPayload:
    return get_experiment_analytics_overview()


@router.get("/analytics/exports", response_model=list[AnalyticsExportDescriptorPayload])
def analytics_exports() -> list[AnalyticsExportDescriptorPayload]:
    return list_experiment_exports()


@router.get("/analytics/exports/{dataset_key}")
def analytics_export_dataset(dataset_key: str, format: str = "csv") -> Response:
    if format != "csv":
        raise HTTPException(status_code=400, detail="Only csv export is supported.")
    try:
        payload, filename = export_experiment_dataset_csv(dataset_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=payload,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/analytics/recommendation-feedback", response_model=RecommendationFeedbackPayload)
def analytics_recommendation_feedback(req: RecommendationFeedbackRequest) -> RecommendationFeedbackPayload:
    try:
        return upsert_recommendation_feedback(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/flashcards/decks", response_model=DeckPayload)
def flashcards_create_deck(req: DeckCreateRequest) -> DeckPayload:
    return create_deck(req)


@router.get("/flashcards/decks/{deck_id}", response_model=DeckDetailPayload)
def flashcards_get_deck(deck_id: str) -> DeckDetailPayload:
    try:
        return get_deck_detail(deck_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/flashcards/decks/{deck_id}", response_model=DeckPayload)
def flashcards_update_deck(deck_id: str, req: DeckUpdateRequest) -> DeckPayload:
    try:
        return update_deck(deck_id, req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/flashcards/decks/{deck_id}")
def flashcards_delete_deck(deck_id: str) -> dict[str, bool]:
    delete_deck(deck_id)
    return {"ok": True}


@router.post("/flashcards/cards", response_model=CardPayload)
def flashcards_create_card(req: CardCreateRequest) -> CardPayload:
    try:
        return create_card(req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/flashcards/cards/{card_id}", response_model=CardPayload)
def flashcards_update_card(card_id: str, req: CardUpdateRequest) -> CardPayload:
    try:
        return update_card(card_id, req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/flashcards/cards/{card_id}")
def flashcards_delete_card(card_id: str) -> dict[str, bool]:
    delete_card(card_id)
    return {"ok": True}


@router.post("/flashcards/import", response_model=FlashcardImportPayload)
def flashcards_import(req: FlashcardImportRequest) -> FlashcardImportPayload:
    return import_flashcards(req)


@router.post("/flashcards/review/next", response_model=ReviewNextPayload)
def flashcards_review_next(req: ReviewNextRequest) -> ReviewNextPayload:
    return next_review_card(req)


@router.post("/flashcards/review/grade", response_model=ReviewGradePayload)
def flashcards_review_grade(req: ReviewGradeRequest) -> ReviewGradePayload:
    try:
        return grade_review(req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/progress/overview", response_model=ProgressOverviewPayload)
def progress_overview(goal: str = "goethe_b2") -> ProgressOverviewPayload:
    return get_progress_overview(goal)


@router.get("/progress/mistakes")
def progress_mistakes(limit: int = 10) -> dict[str, list]:
    return get_top_mistakes(limit)
