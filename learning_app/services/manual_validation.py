from __future__ import annotations

"""Manual human-rating support for validating approximate automated assessment.

The rubrics here are intentionally small and thesis-oriented. They are useful for
agreement analysis, but they do not claim official Goethe scoring validity.
"""

from typing import Any

from ..db import connection_scope
from ..schemas import (
    ManualCriterionDefinition,
    ManualCriterionScorePayload,
    ManualRatingPayload,
    ManualRatingUpsertRequest,
    ManualReviewCandidatePayload,
    ManualRubricDefinition,
    ValidationSampleType,
)
from .common import from_json, make_id, to_json, utc_now_iso

MANUAL_RUBRICS: dict[ValidationSampleType, ManualRubricDefinition] = {
    "writing": ManualRubricDefinition(
        sample_type="writing",
        rubric_key="writing_manual_v1",
        rubric_version="manual_validation_v1",
        title="Writing Validation Rubric",
        note=(
            "Approximate manual rubric for thesis validation of the app's automated feedback. "
            "It is not an official Goethe scoring procedure."
        ),
        criteria=[
            ManualCriterionDefinition(
                key="task_fulfillment",
                label="Task Fulfillment",
                description="Addresses the prompt, covers the main points, and achieves the communicative goal.",
            ),
            ManualCriterionDefinition(
                key="organization_coherence",
                label="Organization and Coherence",
                description="Ideas are structured clearly and linked in a logical way.",
            ),
            ManualCriterionDefinition(
                key="language_accuracy",
                label="Language Accuracy",
                description="Grammar, spelling, and sentence control are sufficiently stable for the target level.",
            ),
            ManualCriterionDefinition(
                key="vocabulary_register",
                label="Vocabulary and Register",
                description="Word choice is reasonably appropriate and the tone fits the task.",
            ),
        ],
    ),
    "speaking": ManualRubricDefinition(
        sample_type="speaking",
        rubric_key="speaking_manual_v1",
        rubric_version="manual_validation_v1",
        title="Speaking Validation Rubric",
        note=(
            "Transcript-based approximate manual rubric for validating the app's speaking assessment. "
            "It does not claim official oral-exam validity and should not be used as official scoring."
        ),
        criteria=[
            ManualCriterionDefinition(
                key="task_response",
                label="Task Response",
                description="Responds to the task and develops relevant content.",
            ),
            ManualCriterionDefinition(
                key="interaction_development",
                label="Interaction and Development",
                description="Keeps the exchange moving and develops ideas clearly across turns.",
            ),
            ManualCriterionDefinition(
                key="coherence_clarity",
                label="Coherence and Clarity",
                description="The response is understandable, ordered, and easy to follow.",
            ),
            ManualCriterionDefinition(
                key="language_control",
                label="Language Control",
                description="Grammar and vocabulary are sufficiently controlled for the target level.",
            ),
        ],
    ),
}


def list_manual_rubrics() -> list[ManualRubricDefinition]:
    return [MANUAL_RUBRICS["writing"], MANUAL_RUBRICS["speaking"]]


def _sample_type_for_attempt(category: str) -> ValidationSampleType | None:
    normalized = str(category or "").strip().lower()
    if normalized == "writing":
        return "writing"
    if normalized == "speaking":
        return "speaking"
    return None


def _artifact_text(sample_type: ValidationSampleType, user_answers: dict[str, Any]) -> str:
    if sample_type == "writing":
        return str(user_answers.get("text") or "").strip()

    transcript = user_answers.get("transcript")
    if isinstance(transcript, list):
        user_lines = [
            str(entry.get("text") or "").strip()
            for entry in transcript
            if str(entry.get("speaker") or "").strip().lower() == "user" and str(entry.get("text") or "").strip()
        ]
        if user_lines:
            return "\n".join(user_lines)
        transcript_lines = [
            f"{str(entry.get('speaker') or '').strip().title()}: {str(entry.get('text') or '').strip()}"
            for entry in transcript
            if str(entry.get("text") or "").strip()
        ]
        if transcript_lines:
            return "\n".join(transcript_lines)

    combined = str(user_answers.get("combined_response") or user_answers.get("last_turn") or "").strip()
    return combined


def _prompt_context(sample_type: ValidationSampleType, title: str, prompt_payload: dict[str, Any]) -> str:
    if sample_type == "writing":
        bullet_points = prompt_payload.get("bullet_points") or []
        parts = [title, str(prompt_payload.get("instructions") or "").strip()]
        if bullet_points:
            parts.append("Leitpunkte: " + " | ".join(str(item).strip() for item in bullet_points if str(item).strip()))
        return "\n".join(part for part in parts if part)

    evaluation_points = prompt_payload.get("evaluation_points") or []
    parts = [
        title,
        str(prompt_payload.get("scenario") or "").strip(),
        str(prompt_payload.get("examiner_prompt") or "").strip(),
    ]
    if evaluation_points:
        parts.append("Bewertungspunkte: " + " | ".join(str(item).strip() for item in evaluation_points if str(item).strip()))
    return "\n".join(part for part in parts if part)


def list_manual_review_candidates(
    *,
    sample_type: ValidationSampleType,
    limit: int = 20,
    reviewer_id: str | None = None,
    only_unrated: bool = True,
) -> list[ManualReviewCandidatePayload]:
    filters = ["attempts.category = ?"]
    params: list[Any] = [sample_type]

    if only_unrated:
        reviewer_key = str(reviewer_id or "").strip()
        if reviewer_key:
            filters.append(
                """
                NOT EXISTS (
                    SELECT 1 FROM manual_ratings mr
                    WHERE mr.attempt_id = attempts.id AND mr.reviewer_id = ?
                )
                """
            )
            params.append(reviewer_key)
        else:
            filters.append("NOT EXISTS (SELECT 1 FROM manual_ratings mr WHERE mr.attempt_id = attempts.id)")

    where_sql = " AND ".join(filters)
    params.append(max(1, min(int(limit), 100)))

    with connection_scope() as conn:
        rows = conn.execute(
            f"""
            SELECT
                attempts.id,
                attempts.category,
                attempts.module,
                attempts.level,
                attempts.score,
                attempts.max_score,
                attempts.percent,
                attempts.assessment_mode,
                attempts.created_at,
                attempts.user_answers_json,
                exercises.title,
                exercises.prompt_json,
                COUNT(manual_ratings.id) AS rating_count
            FROM attempts
            JOIN exercises ON exercises.id = attempts.exercise_id
            LEFT JOIN manual_ratings ON manual_ratings.attempt_id = attempts.id
            WHERE {where_sql}
            GROUP BY attempts.id
            ORDER BY attempts.created_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()

    candidates: list[ManualReviewCandidatePayload] = []
    for row in rows:
        detected_sample_type = _sample_type_for_attempt(row["category"])
        if detected_sample_type != sample_type:
            continue
        user_answers = from_json(row["user_answers_json"]) or {}
        prompt_payload = from_json(row["prompt_json"]) or {}
        candidates.append(
            ManualReviewCandidatePayload(
                attempt_id=row["id"],
                sample_type=sample_type,
                title=row["title"],
                level=row["level"],
                module=row["module"],
                created_at=row["created_at"],
                prompt_context=_prompt_context(sample_type, row["title"], prompt_payload),
                artifact_text=_artifact_text(sample_type, user_answers),
                automated_score=float(row["score"]),
                automated_max_score=float(row["max_score"]),
                automated_percent=float(row["percent"]),
                assessment_mode=str(row["assessment_mode"]),
                rating_count=int(row["rating_count"] or 0),
            )
        )
    return candidates


def _load_attempt_for_rating(conn: Any, attempt_id: str) -> Any:
    return conn.execute(
        """
        SELECT
            attempts.id,
            attempts.category,
            attempts.score,
            attempts.max_score,
            attempts.percent,
            attempts.assessment_mode
        FROM attempts
        WHERE attempts.id = ?
        """,
        (attempt_id,),
    ).fetchone()


def _validated_manual_scores(
    sample_type: ValidationSampleType,
    raw_scores: list[Any],
) -> tuple[list[ManualCriterionScorePayload], float, float]:
    rubric = MANUAL_RUBRICS[sample_type]
    definitions = {criterion.key: criterion for criterion in rubric.criteria}
    ordered_keys = [criterion.key for criterion in rubric.criteria]

    if len(raw_scores) != len(ordered_keys):
        raise ValueError("Alle Rubrikkriterien muessen genau einmal bewertet werden.")

    provided_keys = [str(item.criterion_key).strip() for item in raw_scores]
    if sorted(provided_keys) != sorted(ordered_keys):
        raise ValueError("Die manuelle Bewertung passt nicht zur erwarteten Rubrik.")

    payload_scores: list[ManualCriterionScorePayload] = []
    total_score = 0.0
    max_score = 0.0
    for key in ordered_keys:
        definition = definitions[key]
        source = next(item for item in raw_scores if str(item.criterion_key).strip() == key)
        score = round(float(source.score), 2)
        if score < 0 or score > definition.max_score:
            raise ValueError(f"Der Wert fuer {definition.label} liegt ausserhalb der Rubrik.")
        payload_scores.append(
            ManualCriterionScorePayload(
                criterion_key=definition.key,
                label=definition.label,
                score=score,
                max_score=definition.max_score,
            )
        )
        total_score += score
        max_score += definition.max_score
    return payload_scores, round(total_score, 2), round(max_score, 2)


def _manual_rating_payload_from_row(row: Any) -> ManualRatingPayload:
    criteria = [
        ManualCriterionScorePayload(
            criterion_key=str(item["criterion_key"]),
            label=str(item["label"]),
            score=float(item["score"]),
            max_score=float(item["max_score"]),
        )
        for item in (from_json(row["criteria_scores_json"]) or [])
    ]
    max_score = float(row["max_score"])
    overall_score = float(row["overall_score"])
    percent = round((overall_score / max_score) * 100, 1) if max_score else 0.0
    return ManualRatingPayload(
        rating_id=row["id"],
        attempt_id=row["attempt_id"],
        sample_type=row["sample_type"],
        reviewer_id=row["reviewer_id"],
        reviewer_name=row["reviewer_name"],
        rubric_key=row["rubric_key"],
        rubric_version=row["rubric_version"],
        criteria=criteria,
        overall_score=overall_score,
        max_score=max_score,
        percent=percent,
        notes=row["notes"],
        automated_score=float(row["score"]),
        automated_max_score=float(row["max_score_attempt"]),
        automated_percent=float(row["percent"]),
        assessment_mode=str(row["assessment_mode"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _fetch_manual_rating(conn: Any, rating_id: str) -> Any:
    return conn.execute(
        """
        SELECT
            manual_ratings.*,
            attempts.score,
            attempts.max_score AS max_score_attempt,
            attempts.percent,
            attempts.assessment_mode
        FROM manual_ratings
        JOIN attempts ON attempts.id = manual_ratings.attempt_id
        WHERE manual_ratings.id = ?
        """,
        (rating_id,),
    ).fetchone()


def list_manual_ratings(attempt_id: str) -> list[ManualRatingPayload]:
    with connection_scope() as conn:
        rows = conn.execute(
            """
            SELECT
                manual_ratings.*,
                attempts.score,
                attempts.max_score AS max_score_attempt,
                attempts.percent,
                attempts.assessment_mode
            FROM manual_ratings
            JOIN attempts ON attempts.id = manual_ratings.attempt_id
            WHERE manual_ratings.attempt_id = ?
            ORDER BY manual_ratings.updated_at DESC
            """,
            (attempt_id,),
        ).fetchall()
    return [_manual_rating_payload_from_row(row) for row in rows]


def upsert_manual_rating(req: ManualRatingUpsertRequest) -> ManualRatingPayload:
    reviewer_id = req.reviewer_id.strip()
    reviewer_name = req.reviewer_name.strip()
    now = utc_now_iso()

    with connection_scope() as conn:
        attempt = _load_attempt_for_rating(conn, req.attempt_id)
        if not attempt:
            raise ValueError("Versuch fuer die manuelle Validierung nicht gefunden.")
        sample_type = _sample_type_for_attempt(attempt["category"])
        if not sample_type:
            raise ValueError("Manuelle Validierung ist derzeit nur fuer Writing- und Speaking-Versuche verfuegbar.")

        rubric = MANUAL_RUBRICS[sample_type]
        criteria_payload, overall_score, max_score = _validated_manual_scores(sample_type, req.criteria)
        existing = conn.execute(
            """
            SELECT id, created_at
            FROM manual_ratings
            WHERE attempt_id = ? AND reviewer_id = ? AND rubric_version = ?
            """,
            (req.attempt_id, reviewer_id, rubric.rubric_version),
        ).fetchone()
        rating_id = str(existing["id"]) if existing else make_id("mrating")
        created_at = str(existing["created_at"]) if existing else now

        conn.execute(
            """
            INSERT INTO manual_ratings (
                id, attempt_id, sample_type, rubric_key, rubric_version, reviewer_id, reviewer_name,
                criteria_scores_json, overall_score, max_score, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(attempt_id, reviewer_id, rubric_version) DO UPDATE SET
                reviewer_name = excluded.reviewer_name,
                criteria_scores_json = excluded.criteria_scores_json,
                overall_score = excluded.overall_score,
                max_score = excluded.max_score,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (
                rating_id,
                req.attempt_id,
                sample_type,
                rubric.rubric_key,
                rubric.rubric_version,
                reviewer_id,
                reviewer_name,
                to_json(
                    [
                        {
                            "criterion_key": item.criterion_key,
                            "label": item.label,
                            "score": item.score,
                            "max_score": item.max_score,
                        }
                        for item in criteria_payload
                    ]
                ),
                overall_score,
                max_score,
                req.notes,
                created_at,
                now,
            ),
        )
        row = _fetch_manual_rating(conn, rating_id)
    return _manual_rating_payload_from_row(row)
