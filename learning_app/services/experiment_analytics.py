from __future__ import annotations

"""Read-only thesis analytics layer for experiment reporting and dataset export.

This module sits above the operational learning flows. It should not change how
the learner studies. Its job is to expose stable, reproducible summaries and CSV
exports from the experiment/evaluation tables already populated elsewhere.
"""

import csv
from io import StringIO
from typing import Any

from ..db import connection_scope
from ..schemas import (
    AnalyticsExportDescriptorPayload,
    ExperimentAnalyticsOverviewPayload,
    ExperimentAttemptStrategySummary,
    ExperimentErrorSummary,
    ExperimentManualAgreementSummary,
    ExperimentProgressDailyPoint,
    ExperimentRecommendationSummary,
    ExperimentReviewStrategySummary,
    RecommendationFeedbackPayload,
    RecommendationFeedbackRequest,
)
from .common import make_id, utc_now_iso

# Stable dataset keys used by the analytics endpoints and later by the thesis
# results chapter. Prefer adding new exports here instead of scattering ad-hoc
# SQL across the rest of the application.
EXPORT_DATASETS: dict[str, dict[str, str]] = {
    "attempts": {
        "source_name": "experiment_attempts_export",
        "description": "Raw attempt-level export with strategy labels, recommendation linkage, and exercise metadata.",
        "query": "SELECT * FROM experiment_attempts_export ORDER BY created_at ASC",
    },
    "attempt_strategy_summary": {
        "source_name": "experiment_attempt_strategy_summary",
        "description": "Aggregated attempt outcomes by recommendation, review, and assessment strategy plus skill/module.",
        "query": "SELECT * FROM experiment_attempt_strategy_summary ORDER BY recommendation_strategy, review_strategy, assessment_mode, category, module",
    },
    "progress_daily": {
        "source_name": "experiment_progress_daily_export",
        "description": "Daily progress points for plotting score trends over time by strategy and skill.",
        "query": "SELECT * FROM experiment_progress_daily_export ORDER BY activity_day ASC, recommendation_strategy, review_strategy, assessment_mode, category, module",
    },
    "errors": {
        "source_name": "experiment_error_reduction_export",
        "description": "Per-error recurrence export for repeated-error reduction analysis.",
        "query": "SELECT * FROM experiment_error_reduction_export ORDER BY created_at ASC, skill, tag",
    },
    "error_summary": {
        "source_name": "experiment_error_summary",
        "description": "Aggregated repeated-error rates by strategy and error tag.",
        "query": "SELECT * FROM experiment_error_summary ORDER BY repeat_rate DESC, total_occurrences DESC, skill, tag",
    },
    "reviews": {
        "source_name": "experiment_reviews_export",
        "description": "Raw review-level export with scheduling strategy, recall outcome, and recommendation linkage.",
        "query": "SELECT * FROM experiment_reviews_export ORDER BY reviewed_at ASC",
    },
    "review_retention": {
        "source_name": "experiment_review_retention_export",
        "description": "Derived review-retention export with due-completion and on-time completion flags.",
        "query": "SELECT * FROM experiment_review_retention_export ORDER BY reviewed_at ASC",
    },
    "review_strategy_summary": {
        "source_name": "experiment_review_strategy_summary",
        "description": "Aggregated retention and scheduling-quality metrics by review strategy.",
        "query": "SELECT * FROM experiment_review_strategy_summary ORDER BY review_strategy",
    },
    "recommendations": {
        "source_name": "experiment_recommendations_export",
        "description": "Raw recommendation-event export with strategy labels and event context.",
        "query": "SELECT * FROM experiment_recommendations_export ORDER BY created_at ASC",
    },
    "recommendation_feedback": {
        "source_name": "experiment_recommendation_feedback_export",
        "description": "Per-recommendation export with usefulness feedback and linked attempt/review outcomes.",
        "query": "SELECT * FROM experiment_recommendation_feedback_export ORDER BY created_at ASC",
    },
    "recommendation_summary": {
        "source_name": "experiment_recommendation_summary",
        "description": "Aggregated recommendation follow-through and usefulness metrics by strategy and source.",
        "query": "SELECT * FROM experiment_recommendation_summary ORDER BY recommendation_strategy, source",
    },
    "manual_validation": {
        "source_name": "manual_validation_export",
        "description": "Joined manual-rating export with raw automated assessment payloads for validation analysis.",
        "query": "SELECT * FROM manual_validation_export ORDER BY manual_updated_at ASC",
    },
    "manual_agreement": {
        "source_name": "experiment_manual_agreement_export",
        "description": "Per-rating export with manual-vs-automated score gaps for agreement analysis.",
        "query": "SELECT * FROM experiment_manual_agreement_export ORDER BY manual_updated_at ASC",
    },
    "manual_agreement_summary": {
        "source_name": "experiment_manual_agreement_summary",
        "description": "Aggregated manual-vs-automated agreement metrics by sample type and assessment mode.",
        "query": "SELECT * FROM experiment_manual_agreement_summary ORDER BY sample_type, assessment_mode",
    },
}


def _rows(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connection_scope() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def list_experiment_exports() -> list[AnalyticsExportDescriptorPayload]:
    descriptors: list[AnalyticsExportDescriptorPayload] = []
    with connection_scope() as conn:
        for key, config in EXPORT_DATASETS.items():
            row = conn.execute(f"SELECT COUNT(*) AS total FROM {config['source_name']}").fetchone()
            descriptors.append(
                AnalyticsExportDescriptorPayload(
                    key=key,
                    source_name=config["source_name"],
                    description=config["description"],
                    row_count=int(row["total"] if row else 0),
                )
            )
    return descriptors


def upsert_recommendation_feedback(req: RecommendationFeedbackRequest) -> RecommendationFeedbackPayload:
    recommendation_event_id = req.recommendation_event_id.strip()
    notes = req.notes.strip()
    now = utc_now_iso()

    with connection_scope() as conn:
        event_row = conn.execute(
            """
            SELECT id, source, strategy_label
            FROM recommendation_events
            WHERE id = ?
            """,
            (recommendation_event_id,),
        ).fetchone()
        if not event_row:
            raise ValueError("Recommendation event not found for analytics feedback.")

        existing = conn.execute(
            """
            SELECT id, created_at
            FROM recommendation_feedback
            WHERE recommendation_event_id = ?
            """,
            (recommendation_event_id,),
        ).fetchone()
        feedback_id = str(existing["id"]) if existing else make_id("recofb")
        created_at = str(existing["created_at"]) if existing else now

        conn.execute(
            """
            INSERT INTO recommendation_feedback (
                id, recommendation_event_id, usefulness_score, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(recommendation_event_id) DO UPDATE SET
                usefulness_score = excluded.usefulness_score,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (
                feedback_id,
                recommendation_event_id,
                req.usefulness_score,
                notes,
                created_at,
                now,
            ),
        )

    return RecommendationFeedbackPayload(
        recommendation_event_id=recommendation_event_id,
        recommendation_strategy=str(event_row["strategy_label"]),
        source=str(event_row["source"]),
        usefulness_score=req.usefulness_score,
        notes=notes,
        created_at=created_at,
        updated_at=now,
    )


def get_experiment_analytics_overview() -> ExperimentAnalyticsOverviewPayload:
    return ExperimentAnalyticsOverviewPayload(
        attempt_strategy_summaries=[
            ExperimentAttemptStrategySummary.model_validate(row)
            for row in _rows(
                """
                SELECT *
                FROM experiment_attempt_strategy_summary
                ORDER BY recommendation_strategy, review_strategy, assessment_mode, category, module
                """
            )
        ],
        progress_daily=[
            ExperimentProgressDailyPoint.model_validate(row)
            for row in _rows(
                """
                SELECT *
                FROM experiment_progress_daily_export
                ORDER BY activity_day ASC, recommendation_strategy, review_strategy, assessment_mode, category, module
                """
            )
        ],
        error_summaries=[
            ExperimentErrorSummary.model_validate(row)
            for row in _rows(
                """
                SELECT *
                FROM experiment_error_summary
                ORDER BY repeat_rate DESC, total_occurrences DESC, skill, tag
                """
            )
        ],
        review_strategy_summaries=[
            ExperimentReviewStrategySummary.model_validate(row)
            for row in _rows(
                """
                SELECT *
                FROM experiment_review_strategy_summary
                ORDER BY review_strategy
                """
            )
        ],
        recommendation_summaries=[
            ExperimentRecommendationSummary.model_validate(row)
            for row in _rows(
                """
                SELECT *
                FROM experiment_recommendation_summary
                ORDER BY recommendation_strategy, source
                """
            )
        ],
        manual_agreement_summaries=[
            ExperimentManualAgreementSummary.model_validate(row)
            for row in _rows(
                """
                SELECT *
                FROM experiment_manual_agreement_summary
                ORDER BY sample_type, assessment_mode
                """
            )
        ],
    )


def _spreadsheet_safe_cell(value: Any) -> Any:
    """Neutralize formula-like text at export time; leave numeric values intact."""
    if not isinstance(value, str):
        return value
    offset = 0
    while offset < len(value) and (
        value[offset].isspace() or ord(value[offset]) < 32 or value[offset] == "\ufeff"
    ):
        offset += 1
    if value.startswith(("\t", "\r", "\n")) or value[offset:].startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_experiment_dataset_csv(dataset_key: str) -> tuple[str, str]:
    config = EXPORT_DATASETS.get(dataset_key)
    if not config:
        raise ValueError("Unknown analytics export dataset.")

    with connection_scope() as conn:
        cursor = conn.execute(config["query"])
        rows = cursor.fetchall()
        headers = [column[0] for column in (cursor.description or [])]

    buffer = StringIO()
    writer = csv.writer(buffer)
    if headers:
        writer.writerow(headers)
        for row in rows:
            writer.writerow([_spreadsheet_safe_cell(row[column]) for column in headers])
    return buffer.getvalue(), f"{config['source_name']}.csv"
