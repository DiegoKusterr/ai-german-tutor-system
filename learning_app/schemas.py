from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

LEVEL_PATTERN = r"^(A1|A2|B1|B2|C1|C2)$"

ExamInstitution = Literal["goethe", "telc", "oesd", "testdaf"]
ExamModule = Literal["lesen", "hoeren", "schreiben", "sprechen"]
ExamScope = Literal["module", "full"]
ExerciseType = Literal["fill_blank", "reorder", "transformation", "multiple_choice", "case_choice"]
CardType = Literal["basic", "cloze", "multi_field"]
ChatMode = Literal["fluidez", "correccion_intensa", "roleplay", "goethe_sprechen"]
InterfaceLanguage = Literal["de", "es", "en", "fr", "it", "pt"]
ExplanationLanguage = Literal["es", "de", "en", "fr", "it", "pt"]
RecommendationStrategy = Literal["adaptive_heuristic_v1", "fixed_path_v1"]
ReviewStrategy = Literal["sm2_v1", "fixed_interval_v1"]
ValidationSampleType = Literal["writing", "speaking"]


class ApiChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None
    level: str = Field(default="B2", pattern=LEVEL_PATTERN)
    mode: ChatMode = "fluidez"
    persona_key: str | None = Field(default=None, max_length=40)


class ApiChatResponse(BaseModel):
    reply: str
    conversation_id: str
    mode: ChatMode
    correction: str | None = None
    tips: list[str] = Field(default_factory=list)


class TutorStreamRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None
    level: str = Field(default="B2", pattern=LEVEL_PATTERN)
    mode: ChatMode = "fluidez"
    persona_key: str | None = Field(default=None, max_length=40)


class TutorTtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    turn_id: str | None = None
    sentence_index: int = Field(default=0, ge=0)
    persona_key: str | None = Field(default=None, max_length=40)


class ChatEditMessageRequest(BaseModel):
    conversation_id: str = Field(min_length=1)
    entry_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=2000)


class ChatRestoreMessageRequest(BaseModel):
    conversation_id: str = Field(min_length=1)
    entry_id: str = Field(min_length=1)
    restore_from_entry_id: str = Field(min_length=1)


class ErrorInsight(BaseModel):
    tag: str
    label: str
    description: str
    example: str
    recommendation: str


class StudyTip(BaseModel):
    title: str
    action: str


class ExerciseItem(BaseModel):
    id: str
    prompt: str
    item_type: Literal["mcq", "short", "open", "fill_blank", "reorder", "true_false"]
    section: str | None = None
    section_title: str | None = None
    support_text: str | None = None
    options: list[str] = Field(default_factory=list)
    answer: str
    explanation: str
    points: int = Field(default=1, ge=1, le=100)
    focus_tag: str = "general"
    keywords: list[str] = Field(default_factory=list)
    min_words: int = 0


class ExerciseResultItem(BaseModel):
    item_id: str
    prompt: str
    user_answer: str
    expected_answer: str
    score: float
    max_score: float
    feedback: str
    corrected_version: str | None = None
    status: Literal["empty", "incorrect", "weak", "partial", "strong", "excellent", "correct"] = "partial"
    answered: bool = False
    error_tags: list[ErrorInsight] = Field(default_factory=list)


class OfficialExamRequest(BaseModel):
    level: str = Field(default="B2", pattern=LEVEL_PATTERN)
    scope: ExamScope = "full"
    module: ExamModule = "lesen"


class OfficialExamResource(BaseModel):
    label: str
    url: str
    resource_type: Literal["page", "pdf", "audio", "video", "digital"]
    official: bool = True


class OfficialPracticeSet(BaseModel):
    key: str
    label: str
    audience: str
    description: str = ""
    default_resource_type: Literal["page", "pdf", "audio", "video", "digital"] = "digital"
    resources: list[OfficialExamResource] = Field(default_factory=list)


class OfficialExamScoring(BaseModel):
    max_points: int
    pass_points: int
    raters: str
    criteria: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ExamPart(BaseModel):
    key: str
    title: str
    instructions: str
    task_types: list[str] = Field(default_factory=list)
    recommended_minutes: int = Field(default=0, ge=0)
    item_count: int | None = Field(default=None, ge=1)
    points: int | None = Field(default=None, ge=1)
    response_format: str | None = None
    audio_plays: int | None = Field(default=None, ge=1)
    min_words: int | None = Field(default=None, ge=1)
    notes: list[str] = Field(default_factory=list)


class OfficialExamModule(BaseModel):
    key: str
    label: str
    duration_minutes: int
    prep_minutes: int = 0
    structure: list[str] = Field(default_factory=list)
    parts: list[ExamPart] = Field(default_factory=list)
    scoring: OfficialExamScoring


class OfficialExamPayload(BaseModel):
    institution: Literal["goethe"]
    level: str
    scope: ExamScope
    selected_module: str | None = None
    title: str
    is_modular: bool
    official_version: str
    pass_rule: str
    official_note: str
    page_url: str
    official_page_url: str | None = None
    practice_page_url: str | None = None
    resources: list[OfficialExamResource] = Field(default_factory=list)
    practice_sets: list[OfficialPracticeSet] = Field(default_factory=list)
    modules: list[OfficialExamModule] = Field(default_factory=list)
    mock_calibration: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ExamGenerateRequest(BaseModel):
    level: str = Field(default="B2", pattern=LEVEL_PATTERN)
    institution: ExamInstitution = "goethe"
    scope: ExamScope = "full"
    module: ExamModule = "lesen"
    duration_minutes: int | None = Field(default=None, ge=10, le=240)
    topic: str | None = Field(default=None, max_length=120)
    variant_seed: str | None = Field(default=None, max_length=160)
    question_count: int | None = Field(default=None, ge=1, le=30)
    mock_audio_voice_gender: Literal["auto", "female", "male"] | None = None
    recommendation_event_id: str | None = Field(default=None, min_length=1, max_length=80)


class MockMediaSegment(BaseModel):
    module: str
    part_key: str
    part_title: str
    source_title: str
    script_text: str
    audio_plays: int = Field(default=1, ge=1)
    playback_rate: float = Field(default=1.0, ge=0.6, le=1.2)
    duration_hint_seconds: int = Field(default=0, ge=0)
    audio_key: str | None = None
    audio_url: str | None = None
    audio_provider: str | None = None
    voice_label: str | None = None


class ExamPayload(BaseModel):
    exercise_id: str
    institution: ExamInstitution
    scope: ExamScope = "module"
    module: str
    selected_module: ExamModule | None = None
    level: str
    duration_minutes: int
    title: str
    instructions: str
    official_style_note: str
    source_framework: str
    cefr_focus: list[str] = Field(default_factory=list)
    parts: list[ExamPart] = Field(default_factory=list)
    official_reference: OfficialExamPayload
    items: list[ExerciseItem]
    criteria: list[str]
    variant_seed: str | None = None
    generator_version: str = ""
    generation_mode: str = ""
    calibration_notes: list[str] = Field(default_factory=list)
    validation_notes: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    generation_elapsed_ms: int = Field(default=0, ge=0)
    module_brief_used: bool = False
    mock_audio_voice_gender: Literal["auto", "female", "male"] | None = None
    mock_media_pack: list[MockMediaSegment] = Field(default_factory=list)


class MockGenerationRunPayload(BaseModel):
    run_id: str
    created_at: str
    level: str = Field(pattern=LEVEL_PATTERN)
    module: str
    scope: ExamScope
    variant_seed: str | None = None
    generation_mode: str
    fallback_used: bool = False
    llm_model: str | None = None
    elapsed_ms: int = Field(default=0, ge=0)
    item_count: int = Field(default=0, ge=0)
    media_pack_count: int = Field(default=0, ge=0)
    validation_notes: list[str] = Field(default_factory=list)
    module_brief_used: bool = False


class MockGenerationAggregate(BaseModel):
    level: str = Field(pattern=LEVEL_PATTERN)
    module: str
    total_runs: int = Field(default=0, ge=0)
    fallback_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    average_elapsed_ms: int = Field(default=0, ge=0)
    generation_modes: dict[str, int] = Field(default_factory=dict)


class MockGenerationHealthPayload(BaseModel):
    recent_runs: list[MockGenerationRunPayload] = Field(default_factory=list)
    aggregates: list[MockGenerationAggregate] = Field(default_factory=list)
    window_runs: int = Field(default=0, ge=0)


class ExamSubmitRequest(BaseModel):
    exercise_id: str = Field(min_length=1)
    answers: dict[str, str] = Field(default_factory=dict)
    explanation_language: ExplanationLanguage = "es"


class AttemptSummary(BaseModel):
    attempt_id: str
    exercise_id: str
    title: str
    category: str
    module: str
    level: str
    percent: float
    created_at: str


class SectionScore(BaseModel):
    section_key: str
    label: str
    score: float
    max_score: float
    pass_points: float = 0
    passed: bool
    criteria: list[str] = Field(default_factory=list)
    note: str = ""


class EvaluationPayload(BaseModel):
    attempt_id: str
    exercise_id: str
    title: str
    category: str
    module: str
    level: str
    score: float
    max_score: float
    percent: float
    answered_count: int = Field(default=0, ge=0)
    unanswered_count: int = Field(default=0, ge=0)
    passed: bool = False
    failed_sections: list[str] = Field(default_factory=list)
    summary: str
    corrected_version: str | None = None
    recurring_errors: list[ErrorInsight] = Field(default_factory=list)
    what_to_improve: list[str] = Field(default_factory=list)
    mini_drills: list[str] = Field(default_factory=list)
    study_plan: list[StudyTip] = Field(default_factory=list)
    section_scores: list[SectionScore] = Field(default_factory=list)
    results: list[ExerciseResultItem] = Field(default_factory=list)
    pass_threshold: float = 60.0
    official_alignment: str = ""


class GrammarGenerateRequest(BaseModel):
    level: str = Field(default="B2", pattern=LEVEL_PATTERN)
    focus: str = Field(min_length=2, max_length=120)
    exercise_type: ExerciseType = "fill_blank"
    topic: str | None = Field(default=None, max_length=120)
    count: int = Field(default=8, ge=3, le=15)
    recommendation_event_id: str | None = Field(default=None, min_length=1, max_length=80)


class GrammarTopicSummary(BaseModel):
    key: str
    label: str
    level: str
    category: str
    summary: str


class GrammarTheoryPayload(BaseModel):
    key: str
    label: str
    level: str
    category: str
    summary: str
    when_to_study: str
    core_rules: list[str] = Field(default_factory=list)
    deep_dive: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    common_mistakes: list[str] = Field(default_factory=list)
    memory_hook: str = ""
    related_topics: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


class GrammarPayload(BaseModel):
    exercise_id: str
    topic_key: str
    topic_level: str
    level: str
    focus: str
    exercise_type: ExerciseType
    title: str
    instructions: str
    theory: GrammarTheoryPayload
    items: list[ExerciseItem]
    recommended_review: list[str] = Field(default_factory=list)


class GrammarSubmitRequest(BaseModel):
    exercise_id: str = Field(min_length=1)
    answers: dict[str, str] = Field(default_factory=dict)
    explanation_language: ExplanationLanguage = "es"


class WritingPromptRequest(BaseModel):
    level: str = Field(default="B2", pattern=LEVEL_PATTERN)
    target_exam: ExamInstitution = "goethe"
    text_type: Literal["email_formal", "email_informal", "opinion", "complaint", "application"] = "email_formal"
    topic: str | None = Field(default=None, max_length=120)
    recommendation_event_id: str | None = Field(default=None, min_length=1, max_length=80)


class WritingPromptPayload(BaseModel):
    prompt_id: str
    level: str
    target_exam: ExamInstitution
    text_type: str
    title: str
    instructions: str
    bullet_points: list[str]
    rubric: list[str]
    suggested_words: list[str]
    official_alignment: str = ""


class WritingGradeRequest(BaseModel):
    prompt_id: str = Field(min_length=1)
    text: str = Field(min_length=20, max_length=8000)
    explanation_language: ExplanationLanguage = "es"


class RubricScore(BaseModel):
    criterion: str
    score: float
    max_score: float
    comment: str


class WritingGradePayload(BaseModel):
    attempt_id: str
    prompt_id: str
    level: str
    title: str
    total_score: float
    max_score: float
    percent: float
    corrected_version: str
    rubric: list[RubricScore]
    recurring_errors: list[ErrorInsight]
    what_to_improve: list[str]
    tricks: list[str]
    mini_drills: list[str]
    study_plan: list[StudyTip]
    official_alignment: str = ""


class SpeakingSimulateRequest(BaseModel):
    level: str = Field(default="B2", pattern=LEVEL_PATTERN)
    target_exam: ExamInstitution = "goethe"
    mode: Literal["roleplay", "goethe_sprechen", "daily_conversation"] = "roleplay"
    topic: str | None = Field(default=None, max_length=120)
    recommendation_event_id: str | None = Field(default=None, min_length=1, max_length=80)


class SpeakingSimulationPayload(BaseModel):
    session_id: str
    level: str
    target_exam: ExamInstitution
    mode: str
    title: str
    scenario: str
    examiner_prompt: str
    evaluation_points: list[str]
    suggested_phrases: list[str]
    official_alignment: str = ""


class SpeakingFeedbackRequest(BaseModel):
    session_id: str = Field(min_length=1)
    user_message: str = Field(min_length=2, max_length=3000)
    explanation_language: ExplanationLanguage = "es"


class SpeakingTurnPayload(BaseModel):
    session_id: str
    turn_number: int
    examiner_reply: str
    corrected_version: str
    turn_feedback: list[str]
    error_tags: list[ErrorInsight]
    is_complete: bool
    final_recommendation: list[StudyTip] = Field(default_factory=list)


class VocabFromTopicRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=120)
    level: str = Field(default="B2", pattern=LEVEL_PATTERN)
    count: int = Field(default=12, ge=5, le=40)


class VocabItem(BaseModel):
    id: str
    lemma: str
    pos: Literal["N", "V", "Adj", "Adv", "Expr"]
    gender: str | None = None
    plural: str | None = None
    translation: str
    level: str
    example: str
    collocation: str
    notes: str
    topic: str


class VocabPayload(BaseModel):
    topic: str
    level: str
    items: list[VocabItem]


class DeckCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=240)
    source: str = Field(default="manual", max_length=80)
    tags: list[str] = Field(default_factory=list)


class DeckUpdateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=240)
    tags: list[str] = Field(default_factory=list)


class CardCreateRequest(BaseModel):
    deck_id: str = Field(min_length=1)
    card_type: CardType = "basic"
    front: str = Field(min_length=1, max_length=300)
    back: str = Field(min_length=1, max_length=400)
    extra: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class CardUpdateRequest(BaseModel):
    card_type: CardType = "basic"
    front: str = Field(min_length=1, max_length=300)
    back: str = Field(min_length=1, max_length=400)
    extra: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class FlashcardImportRequest(BaseModel):
    deck_name: str = Field(min_length=2, max_length=120)
    deck_description: str = Field(default="", max_length=240)
    source: str = Field(default="vocab", max_length=80)
    tags: list[str] = Field(default_factory=list)
    items: list[VocabItem] = Field(default_factory=list)
    raw_text: str | None = Field(default=None, max_length=10000)


class CardPayload(BaseModel):
    id: str
    deck_id: str
    card_type: str
    front: str
    back: str
    extra: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    due_date: str
    easiness: float
    interval_days: int
    repetitions: int


class DeckPayload(BaseModel):
    id: str
    name: str
    description: str
    source: str
    tags: list[str]
    total_cards: int
    due_cards: int
    created_at: str
    updated_at: str


class DeckDetailPayload(DeckPayload):
    cards: list[CardPayload] = Field(default_factory=list)


class FlashcardImportPayload(BaseModel):
    deck: DeckPayload
    imported_cards: int


class StarterDeckSummary(BaseModel):
    key: str
    name: str
    description: str
    level: str
    tags: list[str] = Field(default_factory=list)
    card_count: int
    sample_fronts: list[str] = Field(default_factory=list)


class StarterDeckImportPayload(BaseModel):
    starter_deck: StarterDeckSummary
    imported: FlashcardImportPayload


class ReviewNextRequest(BaseModel):
    deck_id: str | None = None
    recommendation_event_id: str | None = Field(default=None, min_length=1, max_length=80)


class ReviewNextPayload(BaseModel):
    card: CardPayload | None = None
    due_count: int
    message: str
    recommendation_event_id: str | None = None


class ReviewGradeRequest(BaseModel):
    card_id: str = Field(min_length=1)
    quality: int = Field(ge=0, le=5)
    recommendation_event_id: str | None = Field(default=None, min_length=1, max_length=80)


class ReviewGradePayload(BaseModel):
    card_id: str
    quality: int
    next_due_date: str
    easiness: float
    interval_days: int
    repetitions: int
    due_count_remaining: int
    review_strategy: ReviewStrategy = "sm2_v1"
    successful_recall: bool = False
    days_since_last_review: int = 0
    days_overdue: int = 0


class PlacementStartRequest(BaseModel):
    level_hint: str | None = Field(default=None, pattern=LEVEL_PATTERN)
    goal_exam: str = Field(default="goethe_b2", max_length=40)


class PlacementSkillEstimate(BaseModel):
    skill: str
    level: str
    confidence: float
    percent: float
    summary: str


class PlacementStartPayload(BaseModel):
    session_id: str
    title: str
    instructions: str
    goal_exam: str
    items: list[ExerciseItem]
    official_note: str


class PlacementSubmitRequest(BaseModel):
    session_id: str = Field(min_length=1)
    answers: dict[str, str] = Field(default_factory=dict)


class PlacementHistoryItem(BaseModel):
    session_id: str
    overall_level: str
    confidence: float
    created_at: str
    recommended_exam: str


class PlacementResultPayload(BaseModel):
    session_id: str
    overall_level: str
    confidence: float
    recommended_exam: str
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    next_level_requirements: list[str] = Field(default_factory=list)
    skill_estimates: list[PlacementSkillEstimate] = Field(default_factory=list)
    roadmap_preview: list[StudyTip] = Field(default_factory=list)
    results: list[ExerciseResultItem] = Field(default_factory=list)
    created_at: str


class RoadmapGenerateRequest(BaseModel):
    current_level: str | None = Field(default=None, pattern=LEVEL_PATTERN)
    target_level: str = Field(default="B2", pattern=LEVEL_PATTERN)
    target_exam: str = Field(default="goethe_b2", max_length=40)
    placement_session_id: str | None = None
    weeks: int = Field(default=8, ge=4, le=24)


class RoadmapWeek(BaseModel):
    week: int
    title: str
    focus: str
    tasks: list[str] = Field(default_factory=list)
    checkpoint: str
    linked_skills: list[str] = Field(default_factory=list)


class RoadmapMilestone(BaseModel):
    title: str
    description: str
    target_week: int


class RoadmapPayload(BaseModel):
    roadmap_id: str
    title: str
    current_level: str
    target_level: str
    target_exam: str
    summary: str
    must_know: list[str] = Field(default_factory=list)
    weekly_plan: list[RoadmapWeek] = Field(default_factory=list)
    milestones: list[RoadmapMilestone] = Field(default_factory=list)
    is_active: bool = False
    created_at: str


class RoadmapActivateRequest(BaseModel):
    roadmap_id: str = Field(min_length=1)


class AppSettingsPayload(BaseModel):
    interface_language: InterfaceLanguage = "de"
    explanation_language: ExplanationLanguage = "es"
    default_goal_exam: str = "goethe_b2"
    default_goal_level: str = Field(default="B2", pattern=LEVEL_PATTERN)


class AppSettingsUpdateRequest(BaseModel):
    interface_language: InterfaceLanguage = "de"
    explanation_language: ExplanationLanguage = "es"
    default_goal_exam: str = "goethe_b2"
    default_goal_level: str = Field(default="B2", pattern=LEVEL_PATTERN)


class RecommendationStrategyOption(BaseModel):
    key: RecommendationStrategy
    label: str
    description: str
    adaptive: bool = False


class RecommendationStrategyPayload(BaseModel):
    active_strategy: RecommendationStrategy = "adaptive_heuristic_v1"
    available_strategies: list[RecommendationStrategyOption] = Field(default_factory=list)


class RecommendationStrategyUpdateRequest(BaseModel):
    strategy: RecommendationStrategy = "adaptive_heuristic_v1"


class ReviewStrategyOption(BaseModel):
    key: ReviewStrategy
    label: str
    description: str
    adaptive: bool = False


class ReviewStrategyPayload(BaseModel):
    active_strategy: ReviewStrategy = "sm2_v1"
    available_strategies: list[ReviewStrategyOption] = Field(default_factory=list)


class ReviewStrategyUpdateRequest(BaseModel):
    strategy: ReviewStrategy = "sm2_v1"


class ManualCriterionDefinition(BaseModel):
    key: str
    label: str
    description: str
    max_score: float = Field(default=5.0, ge=0.5)


class ManualRubricDefinition(BaseModel):
    sample_type: ValidationSampleType
    rubric_key: str
    rubric_version: str
    title: str
    note: str
    criteria: list[ManualCriterionDefinition] = Field(default_factory=list)


class ManualCriterionScoreInput(BaseModel):
    criterion_key: str = Field(min_length=2, max_length=80)
    score: float = Field(ge=0.0, le=5.0)


class ManualCriterionScorePayload(BaseModel):
    criterion_key: str
    label: str
    score: float
    max_score: float


class ManualReviewCandidatePayload(BaseModel):
    attempt_id: str
    sample_type: ValidationSampleType
    title: str
    level: str
    module: str
    created_at: str
    prompt_context: str
    artifact_text: str
    automated_score: float
    automated_max_score: float
    automated_percent: float
    assessment_mode: str
    rating_count: int = 0


class ManualRatingUpsertRequest(BaseModel):
    attempt_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1, max_length=80)
    reviewer_name: str = Field(default="", max_length=120)
    criteria: list[ManualCriterionScoreInput] = Field(default_factory=list, min_length=1)
    notes: str = Field(default="", max_length=4000)


class ManualRatingPayload(BaseModel):
    rating_id: str
    attempt_id: str
    sample_type: ValidationSampleType
    reviewer_id: str
    reviewer_name: str = ""
    rubric_key: str
    rubric_version: str
    criteria: list[ManualCriterionScorePayload] = Field(default_factory=list)
    overall_score: float
    max_score: float
    percent: float
    notes: str = ""
    automated_score: float
    automated_max_score: float
    automated_percent: float
    assessment_mode: str
    created_at: str
    updated_at: str


class RecommendationFeedbackRequest(BaseModel):
    recommendation_event_id: str = Field(min_length=1, max_length=80)
    usefulness_score: int = Field(ge=1, le=5)
    notes: str = Field(default="", max_length=2000)


class RecommendationFeedbackPayload(BaseModel):
    recommendation_event_id: str
    recommendation_strategy: str
    source: str
    usefulness_score: int = Field(ge=1, le=5)
    notes: str = ""
    created_at: str
    updated_at: str


class AnalyticsExportDescriptorPayload(BaseModel):
    key: str
    source_name: str
    description: str
    row_count: int = 0


class ExperimentAttemptStrategySummary(BaseModel):
    recommendation_strategy: str
    review_strategy: str
    assessment_mode: str
    category: str
    module: str
    attempts: int = 0
    average_score: float | None = None
    average_max_score: float | None = None
    average_percent: float | None = None
    launched_from_recommendation_rate: float | None = None
    first_attempt_at: str | None = None
    last_attempt_at: str | None = None


class ExperimentProgressDailyPoint(BaseModel):
    activity_day: str
    recommendation_strategy: str
    review_strategy: str
    assessment_mode: str
    category: str
    module: str
    attempts: int = 0
    average_percent: float | None = None
    launched_from_recommendation_rate: float | None = None


class ExperimentErrorSummary(BaseModel):
    recommendation_strategy: str
    review_strategy: str
    assessment_mode: str
    skill: str
    tag: str
    total_occurrences: int = 0
    repeat_occurrences: int = 0
    repeat_rate: float | None = None
    first_occurrence_at: str | None = None
    latest_occurrence_at: str | None = None


class ExperimentReviewStrategySummary(BaseModel):
    review_strategy: str
    total_reviews: int = 0
    average_quality: float | None = None
    successful_recall_rate: float | None = None
    average_previous_interval_days: float | None = None
    average_next_interval_days: float | None = None
    average_days_since_last_review: float | None = None
    average_days_overdue: float | None = None
    scheduled_reviews: int = 0
    on_time_completion_rate: float | None = None
    overdue_review_rate: float | None = None


class ExperimentRecommendationSummary(BaseModel):
    recommendation_strategy: str
    source: str
    recommendations_shown: int = 0
    recommendations_with_attempts: int = 0
    recommendations_with_reviews: int = 0
    follow_through_rate: float | None = None
    usefulness_responses: int = 0
    average_usefulness_score: float | None = None
    positive_usefulness_rate: float | None = None
    average_linked_attempt_percent: float | None = None
    average_linked_review_success_rate: float | None = None


class ExperimentManualAgreementSummary(BaseModel):
    sample_type: ValidationSampleType
    assessment_mode: str
    ratings: int = 0
    average_manual_percent: float | None = None
    average_automated_percent: float | None = None
    average_absolute_percent_gap: float | None = None
    within_ten_points_rate: float | None = None


class ExperimentAnalyticsOverviewPayload(BaseModel):
    attempt_strategy_summaries: list[ExperimentAttemptStrategySummary] = Field(default_factory=list)
    progress_daily: list[ExperimentProgressDailyPoint] = Field(default_factory=list)
    error_summaries: list[ExperimentErrorSummary] = Field(default_factory=list)
    review_strategy_summaries: list[ExperimentReviewStrategySummary] = Field(default_factory=list)
    recommendation_summaries: list[ExperimentRecommendationSummary] = Field(default_factory=list)
    manual_agreement_summaries: list[ExperimentManualAgreementSummary] = Field(default_factory=list)


class SkillStat(BaseModel):
    skill: str
    average_percent: float
    attempts: int


class ActiveRoadmapSummary(BaseModel):
    roadmap_id: str
    title: str
    target_level: str
    target_exam: str
    next_checkpoint: str


class PassProbabilityStat(BaseModel):
    label: str
    module: str | None = None
    probability_percent: float | None = None
    attempts: int = 0
    average_percent: float | None = None
    basis: Literal["empirisch", "geschaetzt", "keine_daten"] = "keine_daten"
    status: str = ""
    note: str = ""


class ProgressOverviewPayload(BaseModel):
    current_goal: str
    recommendation_strategy: RecommendationStrategy = "adaptive_heuristic_v1"
    recommendation_event_id: str | None = None
    streak_days: int
    due_flashcards: int
    weak_skills: list[SkillStat]
    top_errors: list[ErrorInsight]
    weekly_plan: list[StudyTip]
    full_exam_probability: PassProbabilityStat | None = None
    module_probabilities: list[PassProbabilityStat] = Field(default_factory=list)
    priority_module: str | None = None
    recommended_exam_scope: ExamScope = "full"
    exam_readiness: str = ""
    next_session: StudyTip | None = None
    active_roadmap: ActiveRoadmapSummary | None = None
    latest_placement_level: str | None = None


class MistakeTrendPayload(BaseModel):
    mistakes: list[ErrorInsight]
