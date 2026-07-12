from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import DB_PATH


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connection_scope() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column_name: str, column_sql: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_sql}")


def init_db() -> None:
    """Initialize the local SQLite schema.

    Schema groups are intentionally mixed into one compact database but conceptually
    split into four layers:
    1. operational app data
    2. adaptive/intelligent decision support
    3. thesis evaluation and manual validation
    4. export-oriented analytics views

    Keeping these layers in one file makes local setup reproducible while the table
    and view naming keeps the evaluation surface explicit.
    """
    with connection_scope() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                goal_exam TEXT NOT NULL,
                goal_level TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                user_id INTEGER PRIMARY KEY,
                interface_language TEXT NOT NULL,
                explanation_language TEXT NOT NULL,
                default_goal_exam TEXT NOT NULL,
                default_goal_level TEXT NOT NULL,
                recommendation_strategy TEXT NOT NULL DEFAULT 'adaptive_heuristic_v1',
                review_strategy TEXT NOT NULL DEFAULT 'sm2_v1',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS learning_sessions (
                id TEXT PRIMARY KEY,
                session_type TEXT NOT NULL,
                level TEXT NOT NULL,
                title TEXT NOT NULL,
                target_exam TEXT,
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS exercises (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                module TEXT NOT NULL,
                level TEXT NOT NULL,
                title TEXT NOT NULL,
                prompt_json TEXT NOT NULL,
                answer_json TEXT NOT NULL,
                criteria_json TEXT NOT NULL,
                meta_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attempts (
                id TEXT PRIMARY KEY,
                exercise_id TEXT NOT NULL,
                category TEXT NOT NULL,
                module TEXT NOT NULL,
                level TEXT NOT NULL,
                user_answers_json TEXT NOT NULL,
                score REAL NOT NULL,
                max_score REAL NOT NULL,
                percent REAL NOT NULL,
                feedback_json TEXT NOT NULL,
                corrected_json TEXT NOT NULL,
                error_tags_json TEXT NOT NULL,
                recommendation_strategy TEXT NOT NULL DEFAULT 'adaptive_heuristic_v1',
                review_strategy TEXT NOT NULL DEFAULT 'sm2_v1',
                assessment_mode TEXT NOT NULL DEFAULT 'standard_v1',
                launched_from_recommendation INTEGER NOT NULL DEFAULT 0,
                recommendation_event_id TEXT,
                linked_recommendation_strategy TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (exercise_id) REFERENCES exercises(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS vocab_items (
                id TEXT PRIMARY KEY,
                lemma TEXT NOT NULL,
                pos TEXT NOT NULL,
                gender TEXT,
                plural_form TEXT,
                translation TEXT NOT NULL,
                level TEXT NOT NULL,
                example TEXT NOT NULL,
                collocation TEXT NOT NULL,
                notes TEXT NOT NULL,
                topic TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS decks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                source TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cards (
                id TEXT PRIMARY KEY,
                deck_id TEXT NOT NULL,
                card_type TEXT NOT NULL,
                front TEXT NOT NULL,
                back TEXT NOT NULL,
                extra_json TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                easiness REAL NOT NULL DEFAULT 2.5,
                interval_days INTEGER NOT NULL DEFAULT 0,
                repetitions INTEGER NOT NULL DEFAULT 0,
                due_date TEXT NOT NULL,
                last_reviewed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (deck_id) REFERENCES decks(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id TEXT PRIMARY KEY,
                card_id TEXT NOT NULL,
                quality INTEGER NOT NULL,
                easiness REAL NOT NULL,
                interval_days INTEGER NOT NULL,
                repetitions INTEGER NOT NULL,
                due_date TEXT NOT NULL,
                review_strategy TEXT NOT NULL DEFAULT 'sm2_v1',
                previous_easiness REAL NOT NULL DEFAULT 2.5,
                previous_interval_days INTEGER NOT NULL DEFAULT 0,
                previous_repetitions INTEGER NOT NULL DEFAULT 0,
                previous_due_date TEXT,
                days_since_last_review INTEGER NOT NULL DEFAULT 0,
                days_overdue INTEGER NOT NULL DEFAULT 0,
                successful_recall INTEGER NOT NULL DEFAULT 0,
                launched_from_recommendation INTEGER NOT NULL DEFAULT 0,
                recommendation_event_id TEXT,
                linked_recommendation_strategy TEXT,
                reviewed_at TEXT NOT NULL,
                FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS error_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id TEXT NOT NULL,
                category TEXT NOT NULL,
                skill TEXT NOT NULL,
                tag TEXT NOT NULL,
                example TEXT NOT NULL,
                weight INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (attempt_id) REFERENCES attempts(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS placement_sessions (
                id TEXT PRIMARY KEY,
                level_hint TEXT,
                goal_exam TEXT NOT NULL,
                title TEXT NOT NULL,
                state_json TEXT NOT NULL,
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS roadmaps (
                id TEXT PRIMARY KEY,
                current_level TEXT NOT NULL,
                target_level TEXT NOT NULL,
                target_exam TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                must_know_json TEXT NOT NULL,
                weekly_plan_json TEXT NOT NULL,
                milestones_json TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS starter_deck_imports (
                id TEXT PRIMARY KEY,
                starter_key TEXT NOT NULL,
                deck_id TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                FOREIGN KEY (deck_id) REFERENCES decks(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS mock_generation_runs (
                id TEXT PRIMARY KEY,
                level TEXT NOT NULL,
                module TEXT NOT NULL,
                scope TEXT NOT NULL,
                variant_seed TEXT,
                generation_mode TEXT NOT NULL,
                fallback_used INTEGER NOT NULL DEFAULT 0,
                llm_model TEXT,
                elapsed_ms INTEGER NOT NULL DEFAULT 0,
                item_count INTEGER NOT NULL DEFAULT 0,
                media_pack_count INTEGER NOT NULL DEFAULT 0,
                validation_notes_json TEXT NOT NULL DEFAULT '[]',
                module_brief_used INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS recommendation_events (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                strategy_label TEXT NOT NULL,
                goal_exam TEXT NOT NULL,
                recommended_scope TEXT,
                priority_module TEXT,
                next_action TEXT NOT NULL,
                context_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS recommendation_feedback (
                id TEXT PRIMARY KEY,
                recommendation_event_id TEXT NOT NULL,
                usefulness_score INTEGER NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (recommendation_event_id) REFERENCES recommendation_events(id) ON DELETE CASCADE,
                UNIQUE (recommendation_event_id)
            );

            CREATE TABLE IF NOT EXISTS manual_ratings (
                id TEXT PRIMARY KEY,
                attempt_id TEXT NOT NULL,
                sample_type TEXT NOT NULL,
                rubric_key TEXT NOT NULL,
                rubric_version TEXT NOT NULL,
                reviewer_id TEXT NOT NULL,
                reviewer_name TEXT NOT NULL DEFAULT '',
                criteria_scores_json TEXT NOT NULL DEFAULT '[]',
                overall_score REAL NOT NULL,
                max_score REAL NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (attempt_id) REFERENCES attempts(id) ON DELETE CASCADE,
                UNIQUE (attempt_id, reviewer_id, rubric_version)
            );

            """
        )
        _ensure_column(conn, "app_users", "goal_level", "goal_level TEXT NOT NULL DEFAULT 'B2'")
        _ensure_column(
            conn,
            "app_settings",
            "recommendation_strategy",
            "recommendation_strategy TEXT NOT NULL DEFAULT 'adaptive_heuristic_v1'",
        )
        _ensure_column(
            conn,
            "app_settings",
            "review_strategy",
            "review_strategy TEXT NOT NULL DEFAULT 'sm2_v1'",
        )
        _ensure_column(
            conn,
            "attempts",
            "recommendation_strategy",
            "recommendation_strategy TEXT NOT NULL DEFAULT 'adaptive_heuristic_v1'",
        )
        _ensure_column(
            conn,
            "attempts",
            "review_strategy",
            "review_strategy TEXT NOT NULL DEFAULT 'sm2_v1'",
        )
        _ensure_column(
            conn,
            "attempts",
            "assessment_mode",
            "assessment_mode TEXT NOT NULL DEFAULT 'standard_v1'",
        )
        _ensure_column(
            conn,
            "attempts",
            "launched_from_recommendation",
            "launched_from_recommendation INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            conn,
            "attempts",
            "recommendation_event_id",
            "recommendation_event_id TEXT",
        )
        _ensure_column(
            conn,
            "attempts",
            "linked_recommendation_strategy",
            "linked_recommendation_strategy TEXT",
        )
        _ensure_column(
            conn,
            "reviews",
            "review_strategy",
            "review_strategy TEXT NOT NULL DEFAULT 'sm2_v1'",
        )
        _ensure_column(
            conn,
            "reviews",
            "previous_easiness",
            "previous_easiness REAL NOT NULL DEFAULT 2.5",
        )
        _ensure_column(
            conn,
            "reviews",
            "previous_interval_days",
            "previous_interval_days INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            conn,
            "reviews",
            "previous_repetitions",
            "previous_repetitions INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            conn,
            "reviews",
            "previous_due_date",
            "previous_due_date TEXT",
        )
        _ensure_column(
            conn,
            "reviews",
            "days_since_last_review",
            "days_since_last_review INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            conn,
            "reviews",
            "days_overdue",
            "days_overdue INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            conn,
            "reviews",
            "successful_recall",
            "successful_recall INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            conn,
            "reviews",
            "launched_from_recommendation",
            "launched_from_recommendation INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            conn,
            "reviews",
            "recommendation_event_id",
            "recommendation_event_id TEXT",
        )
        _ensure_column(
            conn,
            "reviews",
            "linked_recommendation_strategy",
            "linked_recommendation_strategy TEXT",
        )
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_attempts_category_created
            ON attempts(category, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_attempts_strategy_created
            ON attempts(recommendation_strategy, assessment_mode, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_attempts_recommendation_event
            ON attempts(recommendation_event_id, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_error_tags_skill_tag
            ON error_tags(skill, tag);

            CREATE INDEX IF NOT EXISTS idx_cards_due_date
            ON cards(due_date);

            CREATE INDEX IF NOT EXISTS idx_placement_created
            ON placement_sessions(created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_roadmaps_active
            ON roadmaps(is_active, updated_at DESC);

            CREATE INDEX IF NOT EXISTS idx_mock_generation_runs_created
            ON mock_generation_runs(created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_mock_generation_runs_level_module
            ON mock_generation_runs(level, module, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_reviews_strategy_created
            ON reviews(review_strategy, reviewed_at DESC);

            CREATE INDEX IF NOT EXISTS idx_reviews_recommendation_event
            ON reviews(recommendation_event_id, reviewed_at DESC);

            CREATE INDEX IF NOT EXISTS idx_recommendation_events_created
            ON recommendation_events(created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_recommendation_events_strategy
            ON recommendation_events(strategy_label, source, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_recommendation_feedback_event
            ON recommendation_feedback(recommendation_event_id, updated_at DESC);

            CREATE INDEX IF NOT EXISTS idx_manual_ratings_attempt
            ON manual_ratings(attempt_id, updated_at DESC);

            CREATE INDEX IF NOT EXISTS idx_manual_ratings_sample_type
            ON manual_ratings(sample_type, updated_at DESC);
            """
        )
        conn.executescript(
            """
            DROP VIEW IF EXISTS experiment_attempts_export;
            CREATE VIEW experiment_attempts_export AS
            SELECT
                attempts.id AS attempt_id,
                attempts.exercise_id,
                exercises.title,
                attempts.category,
                attempts.module,
                attempts.level,
                attempts.score,
                attempts.max_score,
                attempts.percent,
                attempts.recommendation_strategy,
                attempts.review_strategy,
                attempts.assessment_mode,
                attempts.launched_from_recommendation,
                attempts.recommendation_event_id,
                attempts.linked_recommendation_strategy,
                attempts.created_at,
                recommendation_events.source AS linked_recommendation_source,
                recommendation_events.goal_exam AS linked_recommendation_goal_exam,
                exercises.criteria_json,
                exercises.meta_json
            FROM attempts
            JOIN exercises ON exercises.id = attempts.exercise_id
            LEFT JOIN recommendation_events ON recommendation_events.id = attempts.recommendation_event_id;

            DROP VIEW IF EXISTS experiment_reviews_export;
            CREATE VIEW experiment_reviews_export AS
            SELECT
                reviews.id AS review_id,
                reviews.card_id,
                cards.deck_id,
                decks.name AS deck_name,
                cards.card_type,
                reviews.quality,
                reviews.easiness,
                reviews.interval_days,
                reviews.repetitions,
                reviews.due_date,
                reviews.review_strategy,
                reviews.previous_easiness,
                reviews.previous_interval_days,
                reviews.previous_repetitions,
                reviews.previous_due_date,
                reviews.days_since_last_review,
                reviews.days_overdue,
                reviews.successful_recall,
                reviews.launched_from_recommendation,
                reviews.recommendation_event_id,
                reviews.linked_recommendation_strategy,
                reviews.reviewed_at,
                recommendation_events.source AS linked_recommendation_source,
                recommendation_events.goal_exam AS linked_recommendation_goal_exam,
                cards.tags_json
            FROM reviews
            JOIN cards ON cards.id = reviews.card_id
            LEFT JOIN decks ON decks.id = cards.deck_id
            LEFT JOIN recommendation_events ON recommendation_events.id = reviews.recommendation_event_id;

            DROP VIEW IF EXISTS experiment_recommendations_export;
            CREATE VIEW experiment_recommendations_export AS
            SELECT
                recommendation_events.id AS recommendation_event_id,
                recommendation_events.source,
                recommendation_events.strategy_label AS recommendation_strategy,
                recommendation_events.goal_exam,
                recommendation_events.recommended_scope,
                recommendation_events.priority_module,
                recommendation_events.next_action,
                recommendation_events.context_json,
                recommendation_events.created_at
            FROM recommendation_events;

            DROP VIEW IF EXISTS experiment_attempt_strategy_summary;
            CREATE VIEW experiment_attempt_strategy_summary AS
            SELECT
                recommendation_strategy,
                review_strategy,
                assessment_mode,
                category,
                module,
                COUNT(*) AS attempts,
                ROUND(AVG(score), 2) AS average_score,
                ROUND(AVG(max_score), 2) AS average_max_score,
                ROUND(AVG(percent), 1) AS average_percent,
                ROUND(AVG(CASE WHEN launched_from_recommendation = 1 THEN 1.0 ELSE 0.0 END) * 100, 1) AS launched_from_recommendation_rate,
                MIN(created_at) AS first_attempt_at,
                MAX(created_at) AS last_attempt_at
            FROM experiment_attempts_export
            GROUP BY recommendation_strategy, review_strategy, assessment_mode, category, module;

            DROP VIEW IF EXISTS experiment_progress_daily_export;
            CREATE VIEW experiment_progress_daily_export AS
            SELECT
                date(created_at) AS activity_day,
                recommendation_strategy,
                review_strategy,
                assessment_mode,
                category,
                module,
                COUNT(*) AS attempts,
                ROUND(AVG(percent), 1) AS average_percent,
                ROUND(AVG(CASE WHEN launched_from_recommendation = 1 THEN 1.0 ELSE 0.0 END) * 100, 1) AS launched_from_recommendation_rate
            FROM experiment_attempts_export
            GROUP BY date(created_at), recommendation_strategy, review_strategy, assessment_mode, category, module;

            DROP VIEW IF EXISTS experiment_error_reduction_export;
            CREATE VIEW experiment_error_reduction_export AS
            WITH prior_errors AS (
                SELECT
                    error_tags.id AS error_event_id,
                    error_tags.attempt_id,
                    attempts.category,
                    attempts.module,
                    attempts.level,
                    attempts.percent,
                    attempts.recommendation_strategy,
                    attempts.review_strategy,
                    attempts.assessment_mode,
                    error_tags.skill,
                    error_tags.tag,
                    error_tags.example,
                    error_tags.created_at,
                    (
                        SELECT COUNT(*)
                        FROM error_tags prev
                        WHERE prev.skill = error_tags.skill
                          AND prev.tag = error_tags.tag
                          AND prev.id < error_tags.id
                    ) AS previous_occurrences,
                    (
                        SELECT MAX(prev.created_at)
                        FROM error_tags prev
                        WHERE prev.skill = error_tags.skill
                          AND prev.tag = error_tags.tag
                          AND prev.id < error_tags.id
                    ) AS previous_occurrence_at
                FROM error_tags
                JOIN attempts ON attempts.id = error_tags.attempt_id
            )
            SELECT
                error_event_id,
                attempt_id,
                category,
                module,
                level,
                percent,
                recommendation_strategy,
                review_strategy,
                assessment_mode,
                skill,
                tag,
                example,
                created_at,
                previous_occurrences,
                previous_occurrence_at,
                CASE WHEN previous_occurrences > 0 THEN 1 ELSE 0 END AS is_repeat,
                CASE
                    WHEN previous_occurrence_at IS NOT NULL THEN CAST(julianday(date(created_at)) - julianday(date(previous_occurrence_at)) AS INTEGER)
                    ELSE NULL
                END AS days_since_previous_occurrence
            FROM prior_errors;

            DROP VIEW IF EXISTS experiment_error_summary;
            CREATE VIEW experiment_error_summary AS
            SELECT
                recommendation_strategy,
                review_strategy,
                assessment_mode,
                skill,
                tag,
                COUNT(*) AS total_occurrences,
                SUM(is_repeat) AS repeat_occurrences,
                ROUND(AVG(CASE WHEN is_repeat = 1 THEN 1.0 ELSE 0.0 END) * 100, 1) AS repeat_rate,
                MIN(created_at) AS first_occurrence_at,
                MAX(created_at) AS latest_occurrence_at
            FROM experiment_error_reduction_export
            GROUP BY recommendation_strategy, review_strategy, assessment_mode, skill, tag;

            DROP VIEW IF EXISTS experiment_review_retention_export;
            CREATE VIEW experiment_review_retention_export AS
            SELECT
                review_id,
                card_id,
                deck_id,
                deck_name,
                card_type,
                quality,
                easiness,
                interval_days,
                repetitions,
                due_date,
                review_strategy,
                previous_easiness,
                previous_interval_days,
                previous_repetitions,
                previous_due_date,
                days_since_last_review,
                days_overdue,
                successful_recall,
                launched_from_recommendation,
                recommendation_event_id,
                linked_recommendation_strategy,
                reviewed_at,
                linked_recommendation_source,
                linked_recommendation_goal_exam,
                CASE WHEN previous_due_date IS NOT NULL THEN 1 ELSE 0 END AS completed_scheduled_review,
                CASE WHEN previous_due_date IS NOT NULL AND date(reviewed_at) <= date(previous_due_date) THEN 1 ELSE 0 END AS completed_on_time,
                CASE WHEN previous_due_date IS NOT NULL AND date(reviewed_at) > date(previous_due_date) THEN 1 ELSE 0 END AS completed_overdue,
                tags_json
            FROM experiment_reviews_export;

            DROP VIEW IF EXISTS experiment_review_strategy_summary;
            CREATE VIEW experiment_review_strategy_summary AS
            SELECT
                review_strategy,
                COUNT(*) AS total_reviews,
                ROUND(AVG(quality), 2) AS average_quality,
                ROUND(AVG(CASE WHEN successful_recall = 1 THEN 1.0 ELSE 0.0 END) * 100, 1) AS successful_recall_rate,
                ROUND(AVG(previous_interval_days), 2) AS average_previous_interval_days,
                ROUND(AVG(interval_days), 2) AS average_next_interval_days,
                ROUND(AVG(days_since_last_review), 2) AS average_days_since_last_review,
                ROUND(AVG(days_overdue), 2) AS average_days_overdue,
                SUM(CASE WHEN previous_due_date IS NOT NULL THEN 1 ELSE 0 END) AS scheduled_reviews,
                ROUND(
                    CASE
                        WHEN SUM(CASE WHEN previous_due_date IS NOT NULL THEN 1 ELSE 0 END) > 0 THEN
                            SUM(CASE WHEN previous_due_date IS NOT NULL AND date(reviewed_at) <= date(previous_due_date) THEN 1 ELSE 0 END) * 100.0
                            / SUM(CASE WHEN previous_due_date IS NOT NULL THEN 1 ELSE 0 END)
                        ELSE 0
                    END,
                    1
                ) AS on_time_completion_rate,
                ROUND(AVG(CASE WHEN days_overdue > 0 THEN 1.0 ELSE 0.0 END) * 100, 1) AS overdue_review_rate
            FROM experiment_reviews_export
            GROUP BY review_strategy;

            DROP VIEW IF EXISTS experiment_recommendation_feedback_export;
            CREATE VIEW experiment_recommendation_feedback_export AS
            SELECT
                recommendation_events.id AS recommendation_event_id,
                recommendation_events.source,
                recommendation_events.strategy_label AS recommendation_strategy,
                recommendation_events.goal_exam,
                recommendation_events.recommended_scope,
                recommendation_events.priority_module,
                recommendation_events.next_action,
                recommendation_events.context_json,
                recommendation_events.created_at,
                recommendation_feedback.usefulness_score,
                recommendation_feedback.notes AS usefulness_note,
                recommendation_feedback.created_at AS feedback_created_at,
                recommendation_feedback.updated_at AS feedback_updated_at,
                (
                    SELECT COUNT(*)
                    FROM attempts
                    WHERE attempts.recommendation_event_id = recommendation_events.id
                ) AS linked_attempts,
                (
                    SELECT COUNT(*)
                    FROM reviews
                    WHERE reviews.recommendation_event_id = recommendation_events.id
                ) AS linked_reviews,
                ROUND(
                    (
                        SELECT AVG(attempts.percent)
                        FROM attempts
                        WHERE attempts.recommendation_event_id = recommendation_events.id
                    ),
                    1
                ) AS average_linked_attempt_percent,
                ROUND(
                    (
                        SELECT AVG(reviews.quality)
                        FROM reviews
                        WHERE reviews.recommendation_event_id = recommendation_events.id
                    ),
                    2
                ) AS average_linked_review_quality,
                ROUND(
                    (
                        SELECT AVG(CASE WHEN reviews.successful_recall = 1 THEN 1.0 ELSE 0.0 END) * 100
                        FROM reviews
                        WHERE reviews.recommendation_event_id = recommendation_events.id
                    ),
                    1
                ) AS linked_review_success_rate
            FROM recommendation_events
            LEFT JOIN recommendation_feedback ON recommendation_feedback.recommendation_event_id = recommendation_events.id;

            DROP VIEW IF EXISTS experiment_recommendation_summary;
            CREATE VIEW experiment_recommendation_summary AS
            SELECT
                recommendation_strategy,
                source,
                COUNT(*) AS recommendations_shown,
                SUM(CASE WHEN linked_attempts > 0 THEN 1 ELSE 0 END) AS recommendations_with_attempts,
                SUM(CASE WHEN linked_reviews > 0 THEN 1 ELSE 0 END) AS recommendations_with_reviews,
                ROUND(AVG(CASE WHEN linked_attempts > 0 OR linked_reviews > 0 THEN 1.0 ELSE 0.0 END) * 100, 1) AS follow_through_rate,
                SUM(CASE WHEN usefulness_score IS NOT NULL THEN 1 ELSE 0 END) AS usefulness_responses,
                ROUND(AVG(usefulness_score), 2) AS average_usefulness_score,
                ROUND(
                    AVG(
                        CASE
                            WHEN usefulness_score IS NOT NULL THEN CASE WHEN usefulness_score >= 4 THEN 1.0 ELSE 0.0 END
                            ELSE NULL
                        END
                    ) * 100,
                    1
                ) AS positive_usefulness_rate,
                ROUND(AVG(average_linked_attempt_percent), 1) AS average_linked_attempt_percent,
                ROUND(AVG(linked_review_success_rate), 1) AS average_linked_review_success_rate
            FROM experiment_recommendation_feedback_export
            GROUP BY recommendation_strategy, source;

            DROP VIEW IF EXISTS experiment_manual_agreement_export;
            CREATE VIEW experiment_manual_agreement_export AS
            SELECT
                manual_ratings.id AS rating_id,
                manual_ratings.attempt_id,
                manual_ratings.sample_type,
                manual_ratings.rubric_key,
                manual_ratings.rubric_version,
                manual_ratings.reviewer_id,
                manual_ratings.reviewer_name,
                manual_ratings.notes,
                attempts.category AS automated_category,
                attempts.module,
                attempts.level,
                attempts.assessment_mode,
                attempts.recommendation_strategy,
                attempts.review_strategy,
                exercises.title AS exercise_title,
                manual_ratings.overall_score AS manual_score,
                manual_ratings.max_score AS manual_max_score,
                ROUND(
                    CASE
                        WHEN manual_ratings.max_score > 0 THEN (manual_ratings.overall_score / manual_ratings.max_score) * 100
                        ELSE 0
                    END,
                    1
                ) AS manual_percent,
                attempts.score AS automated_score,
                attempts.max_score AS automated_max_score,
                attempts.percent AS automated_percent,
                ROUND(
                    (
                        CASE
                            WHEN manual_ratings.max_score > 0 THEN (manual_ratings.overall_score / manual_ratings.max_score) * 100
                            ELSE 0
                        END
                    ) - attempts.percent,
                    1
                ) AS percent_gap,
                ROUND(
                    ABS(
                        (
                            CASE
                                WHEN manual_ratings.max_score > 0 THEN (manual_ratings.overall_score / manual_ratings.max_score) * 100
                                ELSE 0
                            END
                        ) - attempts.percent
                    ),
                    1
                ) AS absolute_percent_gap,
                manual_ratings.created_at AS manual_created_at,
                manual_ratings.updated_at AS manual_updated_at
            FROM manual_ratings
            JOIN attempts ON attempts.id = manual_ratings.attempt_id
            JOIN exercises ON exercises.id = attempts.exercise_id;

            DROP VIEW IF EXISTS experiment_manual_agreement_summary;
            CREATE VIEW experiment_manual_agreement_summary AS
            SELECT
                sample_type,
                assessment_mode,
                COUNT(*) AS ratings,
                ROUND(AVG(manual_percent), 1) AS average_manual_percent,
                ROUND(AVG(automated_percent), 1) AS average_automated_percent,
                ROUND(AVG(absolute_percent_gap), 1) AS average_absolute_percent_gap,
                ROUND(AVG(CASE WHEN absolute_percent_gap <= 10 THEN 1.0 ELSE 0.0 END) * 100, 1) AS within_ten_points_rate
            FROM experiment_manual_agreement_export
            GROUP BY sample_type, assessment_mode;

            DROP VIEW IF EXISTS manual_validation_export;
            CREATE VIEW manual_validation_export AS
            SELECT
                manual_ratings.id AS rating_id,
                manual_ratings.attempt_id,
                manual_ratings.sample_type,
                manual_ratings.rubric_key,
                manual_ratings.rubric_version,
                manual_ratings.reviewer_id,
                manual_ratings.reviewer_name,
                manual_ratings.criteria_scores_json,
                manual_ratings.overall_score AS manual_score,
                manual_ratings.max_score AS manual_max_score,
                ROUND(
                    CASE
                        WHEN manual_ratings.max_score > 0 THEN (manual_ratings.overall_score / manual_ratings.max_score) * 100
                        ELSE 0
                    END,
                    1
                ) AS manual_percent,
                manual_ratings.notes,
                manual_ratings.created_at AS manual_created_at,
                manual_ratings.updated_at AS manual_updated_at,
                attempts.category AS automated_category,
                attempts.module,
                attempts.level,
                attempts.score AS automated_score,
                attempts.max_score AS automated_max_score,
                attempts.percent AS automated_percent,
                attempts.assessment_mode,
                attempts.recommendation_strategy,
                attempts.review_strategy,
                attempts.launched_from_recommendation,
                attempts.recommendation_event_id,
                attempts.linked_recommendation_strategy,
                attempts.user_answers_json,
                attempts.feedback_json,
                attempts.corrected_json,
                attempts.error_tags_json,
                exercises.title AS exercise_title,
                exercises.prompt_json,
                exercises.criteria_json,
                exercises.meta_json
            FROM manual_ratings
            JOIN attempts ON attempts.id = manual_ratings.attempt_id
            JOIN exercises ON exercises.id = attempts.exercise_id;
            """
        )
