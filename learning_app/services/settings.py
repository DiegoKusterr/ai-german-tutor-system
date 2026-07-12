from __future__ import annotations

from ..config import (
    DEFAULT_EXPLANATION_LANGUAGE,
    DEFAULT_GOAL_EXAM,
    DEFAULT_RECOMMENDATION_STRATEGY,
    DEFAULT_REVIEW_STRATEGY,
    DEFAULT_UI_LANGUAGE,
    LOCAL_USER_ID,
)
from ..db import connection_scope
from ..schemas import (
    AppSettingsPayload,
    AppSettingsUpdateRequest,
    RecommendationStrategyOption,
    RecommendationStrategyPayload,
    RecommendationStrategyUpdateRequest,
    ReviewStrategyOption,
    ReviewStrategyPayload,
    ReviewStrategyUpdateRequest,
)
from .common import save_recommendation_event, utc_now_iso


def _ensure_settings_row(conn) -> None:
    row = conn.execute("SELECT user_id FROM app_settings WHERE user_id = ?", (LOCAL_USER_ID,)).fetchone()
    if row:
        return
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO app_settings (
            user_id, interface_language, explanation_language, default_goal_exam,
            default_goal_level, recommendation_strategy, review_strategy, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            LOCAL_USER_ID,
            DEFAULT_UI_LANGUAGE,
            DEFAULT_EXPLANATION_LANGUAGE,
            DEFAULT_GOAL_EXAM,
            "B2",
            DEFAULT_RECOMMENDATION_STRATEGY,
            DEFAULT_REVIEW_STRATEGY,
            now,
            now,
        ),
    )


def _strategy_options() -> list[RecommendationStrategyOption]:
    return [
        RecommendationStrategyOption(
            key="adaptive_heuristic_v1",
            label="Adaptive Recommendation",
            description="Uses current progress, recent errors, and exam signals to choose the next practice focus.",
            adaptive=True,
        ),
        RecommendationStrategyOption(
            key="fixed_path_v1",
            label="Fixed Path Baseline",
            description="Uses a simple non-personalized sequence with a predefined module order and periodic full mocks.",
            adaptive=False,
        ),
    ]


def _review_strategy_options() -> list[ReviewStrategyOption]:
    return [
        ReviewStrategyOption(
            key="sm2_v1",
            label="Performance-Based SM-2",
            description="Uses review quality to update interval length, repetition count, and ease-like state.",
            adaptive=True,
        ),
        ReviewStrategyOption(
            key="fixed_interval_v1",
            label="Fixed Interval Baseline",
            description="Uses a simple fixed interval ladder with coarse pass/fail progression and no ease adaptation.",
            adaptive=False,
        ),
    ]


def get_settings() -> AppSettingsPayload:
    with connection_scope() as conn:
        _ensure_settings_row(conn)
        row = conn.execute("SELECT * FROM app_settings WHERE user_id = ?", (LOCAL_USER_ID,)).fetchone()
        return AppSettingsPayload(
            interface_language=row["interface_language"],
            explanation_language=row["explanation_language"],
            default_goal_exam=row["default_goal_exam"],
            default_goal_level=row["default_goal_level"],
        )


def update_settings(req: AppSettingsUpdateRequest) -> AppSettingsPayload:
    now = utc_now_iso()
    with connection_scope() as conn:
        _ensure_settings_row(conn)
        strategy_row = conn.execute(
            "SELECT recommendation_strategy, review_strategy FROM app_settings WHERE user_id = ?",
            (LOCAL_USER_ID,),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO app_settings (
                user_id, interface_language, explanation_language, default_goal_exam, default_goal_level,
                recommendation_strategy, review_strategy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                interface_language = excluded.interface_language,
                explanation_language = excluded.explanation_language,
                default_goal_exam = excluded.default_goal_exam,
                default_goal_level = excluded.default_goal_level,
                updated_at = excluded.updated_at
            """,
            (
                LOCAL_USER_ID,
                req.interface_language,
                req.explanation_language,
                req.default_goal_exam,
                req.default_goal_level,
                str(strategy_row["recommendation_strategy"] if strategy_row else DEFAULT_RECOMMENDATION_STRATEGY),
                str(strategy_row["review_strategy"] if strategy_row else DEFAULT_REVIEW_STRATEGY),
                now,
                now,
            ),
        )
        conn.execute(
            "UPDATE app_users SET goal_exam = ?, goal_level = ?, updated_at = ? WHERE id = ?",
            (req.default_goal_exam, req.default_goal_level, now, LOCAL_USER_ID),
        )
    return get_settings()


def get_recommendation_strategy() -> RecommendationStrategyPayload:
    with connection_scope() as conn:
        _ensure_settings_row(conn)
        row = conn.execute(
            "SELECT recommendation_strategy FROM app_settings WHERE user_id = ?",
            (LOCAL_USER_ID,),
        ).fetchone()
    active = str((row["recommendation_strategy"] if row else DEFAULT_RECOMMENDATION_STRATEGY) or DEFAULT_RECOMMENDATION_STRATEGY)
    return RecommendationStrategyPayload(
        active_strategy=active,
        available_strategies=_strategy_options(),
    )


def update_recommendation_strategy(req: RecommendationStrategyUpdateRequest) -> RecommendationStrategyPayload:
    now = utc_now_iso()
    with connection_scope() as conn:
        _ensure_settings_row(conn)
        goal_row = conn.execute(
            "SELECT default_goal_exam FROM app_settings WHERE user_id = ?",
            (LOCAL_USER_ID,),
        ).fetchone()
        conn.execute(
            """
            UPDATE app_settings
            SET recommendation_strategy = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (req.strategy, now, LOCAL_USER_ID),
        )
    save_recommendation_event(
        source="strategy_assignment",
        goal_exam=str(goal_row["default_goal_exam"] if goal_row else DEFAULT_GOAL_EXAM),
        next_action=f"Recommendation strategy set to {req.strategy}.",
        recommended_scope="strategy_assignment",
        priority_module=None,
        context_payload={"assigned_strategy": req.strategy},
        strategy_label=req.strategy,
    )
    return get_recommendation_strategy()


def get_review_strategy() -> ReviewStrategyPayload:
    with connection_scope() as conn:
        _ensure_settings_row(conn)
        row = conn.execute(
            "SELECT review_strategy FROM app_settings WHERE user_id = ?",
            (LOCAL_USER_ID,),
        ).fetchone()
    active = str((row["review_strategy"] if row else DEFAULT_REVIEW_STRATEGY) or DEFAULT_REVIEW_STRATEGY)
    return ReviewStrategyPayload(
        active_strategy=active,
        available_strategies=_review_strategy_options(),
    )


def update_review_strategy(req: ReviewStrategyUpdateRequest) -> ReviewStrategyPayload:
    now = utc_now_iso()
    with connection_scope() as conn:
        _ensure_settings_row(conn)
        conn.execute(
            """
            UPDATE app_settings
            SET review_strategy = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (req.strategy, now, LOCAL_USER_ID),
        )
    return get_review_strategy()
