"""Service exports grouped by repository layer.

Operational product services, adaptive-learning services, and thesis-evaluation
services remain in the same package for compactness, but are grouped below so the
separation is visible in code review and maintenance work.
"""

# Operational flashcard/product services.
from .flashcards import (
    create_card,
    create_deck,
    delete_card,
    delete_deck,
    get_deck_detail,
    grade_review,
    import_flashcards,
    import_starter_deck,
    list_decks,
    list_starter_decks,
    next_review_card,
    update_card,
    update_deck,
)

# Thesis analytics and export services.
from .experiment_analytics import (
    export_experiment_dataset_csv,
    get_experiment_analytics_overview,
    list_experiment_exports,
    upsert_recommendation_feedback,
)

# Operational and adaptive learning workflows.
from .learning import (
    generate_exam,
    generate_grammar,
    generate_speaking_session,
    generate_vocab,
    generate_writing_prompt,
    get_official_exam,
    get_official_resource,
    get_grammar_catalog,
    get_grammar_theory,
    submit_exam,
    submit_grammar,
    submit_speaking_turn,
    submit_writing,
)

# Supporting media and validation layers.
from .mock_audio import get_mock_audio_file
from .manual_validation import list_manual_review_candidates, list_manual_ratings, list_manual_rubrics, upsert_manual_rating
from .mock_telemetry import get_mock_generation_health, list_mock_generation_runs, save_mock_generation_run
from .placement import list_placement_history, start_placement, submit_placement
from .progress import get_progress_overview, get_top_mistakes, list_exam_history
from .roadmap import activate_roadmap, generate_roadmap, get_current_roadmap

# Strategy configuration and reproducibility controls.
from .settings import (
    get_recommendation_strategy,
    get_review_strategy,
    get_settings,
    update_recommendation_strategy,
    update_review_strategy,
    update_settings,
)

__all__ = [
    "activate_roadmap",
    "create_card",
    "create_deck",
    "delete_card",
    "delete_deck",
    "export_experiment_dataset_csv",
    "generate_exam",
    "generate_grammar",
    "generate_roadmap",
    "generate_speaking_session",
    "generate_vocab",
    "generate_writing_prompt",
    "get_current_roadmap",
    "get_deck_detail",
    "get_mock_audio_file",
    "get_mock_generation_health",
    "get_official_exam",
    "get_official_resource",
    "get_experiment_analytics_overview",
    "get_grammar_catalog",
    "get_grammar_theory",
    "get_progress_overview",
    "get_recommendation_strategy",
    "get_review_strategy",
    "get_settings",
    "get_top_mistakes",
    "grade_review",
    "import_flashcards",
    "import_starter_deck",
    "list_decks",
    "list_exam_history",
    "list_experiment_exports",
    "list_manual_ratings",
    "list_manual_review_candidates",
    "list_manual_rubrics",
    "list_mock_generation_runs",
    "list_placement_history",
    "list_starter_decks",
    "next_review_card",
    "start_placement",
    "save_mock_generation_run",
    "submit_exam",
    "submit_grammar",
    "submit_placement",
    "submit_speaking_turn",
    "submit_writing",
    "update_card",
    "update_deck",
    "update_recommendation_strategy",
    "update_review_strategy",
    "update_settings",
    "upsert_recommendation_feedback",
    "upsert_manual_rating",
]
