from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from math import exp
from typing import Any

from ..db import connection_scope
from ..schemas import ActiveRoadmapSummary, AttemptSummary, PassProbabilityStat, ProgressOverviewPayload, SkillStat, StudyTip
from .common import (
    build_error_insight,
    build_study_plan,
    current_recommendation_strategy,
    save_recommendation_event,
    today_iso,
)

EXAM_MODULES = {"lesen", "hoeren", "schreiben", "sprechen"}
MODULE_LABELS = {"lesen": "Lesen", "hoeren": "Hören", "schreiben": "Schreiben", "sprechen": "Sprechen"}
READINESS_NOTE = "Heuristischer Übungsindikator; keine validierte Bestehenswahrscheinlichkeit."
FIXED_PATH_SEQUENCE: list[tuple[str | None, str]] = [
    ("lesen", "module"),
    ("hoeren", "module"),
    ("schreiben", "module"),
    ("sprechen", "module"),
    (None, "full"),
]


def _module_label(module: str | None) -> str:
    if not module:
        return "Gesamtprüfung"
    return MODULE_LABELS.get(module, module.title())


def _goal_level(goal: str) -> str:
    token = str(goal).split("_")[-1].upper()
    return token if token in {"A1", "A2", "B1", "B2", "C1", "C2"} else "B2"


def _probability_status(probability_percent: float | None) -> str:
    if probability_percent is None:
        return "Noch keine Schätzung"
    if probability_percent >= 80:
        return "Sehr gute Tendenz"
    if probability_percent >= 65:
        return "Solide Tendenz"
    if probability_percent >= 50:
        return "Knapp und instabil"
    return "Kritisch"


def _trend_metrics(scores: list[float]) -> tuple[float, str]:
    if not scores:
        return 0.0, "Noch keine Trendlinie."
    if len(scores) == 1:
        return 0.0, "Nur ein Versuch vorhanden; Trend noch offen."

    recent_window = scores[: min(3, len(scores))]
    previous_window = scores[min(3, len(scores)) : min(6, len(scores))]
    recent_average = sum(recent_window) / len(recent_window)
    previous_average = sum(previous_window) / len(previous_window) if previous_window else scores[-1]
    delta = recent_average - previous_average
    pass_streak = 0
    for value in scores:
        if value >= 60.0:
            pass_streak += 1
            continue
        break
    trend_bonus = max(-0.12, min(0.12, (delta / 100.0) * 0.65 + pass_streak * 0.018))
    if delta >= 8:
        return trend_bonus, f"Trend klar steigend ({delta:+.1f} Punkte)."
    if delta >= 3:
        return trend_bonus, f"Trend leicht steigend ({delta:+.1f} Punkte)."
    if delta <= -8:
        return trend_bonus, f"Trend klar fallend ({delta:+.1f} Punkte)."
    if delta <= -3:
        return trend_bonus, f"Trend leicht fallend ({delta:+.1f} Punkte)."
    return trend_bonus, f"Trend weitgehend stabil ({delta:+.1f} Punkte)."


def _score_to_probability(
    percent: float,
    attempts: int = 0,
    pass_rate: float | None = None,
    recent_percent: float | None = None,
    trend_bonus: float = 0.0,
) -> float:
    score_signal = 1 / (1 + exp(-((percent - 60.0) / 7.5)))
    recent_signal = 1 / (1 + exp(-(((recent_percent if recent_percent is not None else percent) - 60.0) / 6.0)))
    empirical_signal = pass_rate if pass_rate is not None else score_signal
    certainty_bonus = min(attempts, 5) * 0.025
    probability = (0.38 * score_signal) + (0.25 * recent_signal) + (0.32 * empirical_signal) + certainty_bonus + trend_bonus
    return round(max(5.0, min(97.0, probability * 100)), 1)


def _build_probability_stat(
    *,
    label: str,
    module: str | None,
    scores: list[float],
    inferred_percent: float | None = None,
    note_hint: str = "",
) -> PassProbabilityStat:
    if scores:
        average_percent = round(sum(scores) / len(scores), 1)
        recent_percent = round(sum(scores[:3]) / min(len(scores), 3), 1)
        pass_rate = sum(1 for value in scores if value >= 60.0) / len(scores)
        trend_bonus, trend_note = _trend_metrics(scores)
        probability_percent = _score_to_probability(
            average_percent,
            attempts=len(scores),
            pass_rate=pass_rate,
            recent_percent=recent_percent,
            trend_bonus=trend_bonus,
        )
        basis = "empirisch" if len(scores) >= 2 else "geschaetzt"
        note = f"{len(scores)} Prüfungsversuche · Schnitt {average_percent}% · {trend_note} {READINESS_NOTE}"
        return PassProbabilityStat(
            label=label,
            module=module,
            probability_percent=probability_percent,
            attempts=len(scores),
            average_percent=average_percent,
            basis=basis,
            status=_probability_status(probability_percent),
            note=note,
        )
    if inferred_percent is not None:
        probability_percent = _score_to_probability(inferred_percent, attempts=0, recent_percent=inferred_percent)
        return PassProbabilityStat(
            label=label,
            module=module,
            probability_percent=probability_percent,
            attempts=0,
            average_percent=round(inferred_percent, 1),
            basis="geschaetzt",
            status=_probability_status(probability_percent),
            note=f"{note_hint or 'Geschätzt aus vorhandenen Prüfungsmodulen.'} {READINESS_NOTE}",
        )
    return PassProbabilityStat(
        label=label,
        module=module,
        probability_percent=None,
        attempts=0,
        average_percent=None,
        basis="keine_daten",
        status=_probability_status(None),
        note=f"{note_hint or 'Noch keine Prüfungsdaten auf dem Zielniveau vorhanden.'} {READINESS_NOTE}",
    )


def _streak_days(conn: Any) -> int:
    rows = conn.execute("SELECT DISTINCT substr(created_at, 1, 10) AS day FROM attempts ORDER BY day DESC").fetchall()
    if not rows:
        return 0
    days = {date.fromisoformat(row["day"]) for row in rows}
    streak = 0
    cursor = date.today()
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def list_exam_history() -> list[AttemptSummary]:
    with connection_scope() as conn:
        rows = conn.execute(
            """
            SELECT attempts.id, attempts.exercise_id, attempts.category, attempts.module, attempts.level,
                   attempts.percent, attempts.created_at, exercises.title
            FROM attempts
            JOIN exercises ON exercises.id = attempts.exercise_id
            WHERE attempts.category = 'exam'
            ORDER BY attempts.created_at DESC
            LIMIT 40
            """
        ).fetchall()
    return [
        AttemptSummary(
            attempt_id=row["id"],
            exercise_id=row["exercise_id"],
            title=row["title"],
            category=row["category"],
            module=row["module"],
            level=row["level"],
            percent=float(row["percent"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_top_mistakes(limit: int = 10) -> dict[str, list]:
    with connection_scope() as conn:
        rows = conn.execute(
            """
            SELECT tag, example, COUNT(*) AS total
            FROM error_tags
            GROUP BY tag, example
            ORDER BY total DESC, tag ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    mistakes = [
        build_error_insight(
            row["tag"],
            row["example"],
            f"Apareció {row['total']} veces en tus intentos recientes.",
        )
        for row in rows
    ]
    return {"mistakes": mistakes}


def _active_roadmap_summary(conn: Any) -> ActiveRoadmapSummary | None:
    row = conn.execute(
        "SELECT id, title, target_level, target_exam, weekly_plan_json FROM roadmaps WHERE is_active = 1 ORDER BY updated_at DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    import json

    weekly = json.loads(row["weekly_plan_json"])
    next_checkpoint = weekly[0]["checkpoint"] if weekly else "Kein Checkpoint vorhanden."
    return ActiveRoadmapSummary(
        roadmap_id=row["id"],
        title=row["title"],
        target_level=row["target_level"],
        target_exam=row["target_exam"],
        next_checkpoint=next_checkpoint,
    )


def _adaptive_progress_recommendation(
    *,
    goal: str,
    exam_attempts: int,
    exam_average: float,
    priority_module: str | None,
    priority_module_score: float | None,
    top_errors: list[Any],
) -> tuple[str, str, StudyTip | None, list[StudyTip], dict[str, Any]]:
    if exam_attempts == 0:
        recommended_scope = "full"
        exam_readiness = "Noch keine Prüfungsdaten vorhanden. Starten Sie mit einer ersten Gesamtprüfung als Standortbestimmung."
        next_session = StudyTip(
            title="Nächste Session",
            action="Bearbeiten Sie jetzt eine vollständige Gesamtprüfung im Stil Ihrer Zielprüfung und notieren Sie danach die zwei schwächsten Module.",
        )
    elif priority_module and priority_module_score is not None and (priority_module_score < 60 or exam_average < 60):
        recommended_scope = "module"
        exam_readiness = (
            f"Die Gesamtprüfung ist noch nicht stabil genug ({exam_average}%). "
            f"Arbeiten Sie zuerst gezielt am Modul {_module_label(priority_module)}."
        )
        next_session = StudyTip(
            title="Nächste Session",
            action=f"Trainieren Sie heute nur {_module_label(priority_module)} unter Zeitdruck und wiederholen Sie danach Ihre letzten Fehler aus diesem Modul.",
        )
    elif exam_average < 75:
        recommended_scope = "full"
        exam_readiness = (
            f"Sie sind in der prüfungsnahen Übergangsphase ({exam_average}%). "
            "Wechseln Sie jetzt zwischen Gesamtprüfung und gezieltem Nachtraining der schwächsten Teilbereiche."
        )
        next_session = StudyTip(
            title="Nächste Session",
            action=(
                f"Bearbeiten Sie eine vollständige Gesamtprüfung. "
                f"Falls {_module_label(priority_module) if priority_module else 'ein Modul'} danach unter 60% bleibt, trainieren Sie es sofort separat nach."
            ),
        )
    else:
        recommended_scope = "full"
        exam_readiness = (
            f"Die Gesamtprüfung ist aktuell sinnvoll ({exam_average}%). "
            "Jetzt geht es darum, die Leistung über mehrere komplette Durchläufe zu stabilisieren."
        )
        next_session = StudyTip(
            title="Nächste Session",
            action="Bearbeiten Sie eine weitere vollständige Gesamtprüfung unter Echtzeitbedingungen und prüfen Sie danach nur noch die Fehler mit dem größten Punkteverlust.",
        )

    weekly_plan = build_study_plan(
        [error.tag for error in top_errors],
        goal,
        priority_module=priority_module,
        recommended_scope=recommended_scope,
    )
    return recommended_scope, exam_readiness, next_session, weekly_plan, {"mode": "adaptive"}


def _fixed_path_recommendation(
    *,
    exam_attempts: int,
) -> tuple[str | None, str, StudyTip | None, list[StudyTip], dict[str, Any]]:
    cycle_index = exam_attempts % len(FIXED_PATH_SEQUENCE)
    fixed_module, recommended_scope = FIXED_PATH_SEQUENCE[cycle_index]
    sequence_labels = [
        _module_label(module) if module else "Gesamtprüfung"
        for module, _ in FIXED_PATH_SEQUENCE
    ]
    exam_readiness = (
        "Vergleichsbedingung aktiv: Die App folgt jetzt einem festen, nicht personalisierten Übungspfad "
        "und ignoriert aktuelle Fehlertrends für die Empfehlung."
    )
    if recommended_scope == "full":
        next_session = StudyTip(
            title="Nächste Session",
            action="Bearbeiten Sie die nächste vollständige Gesamtprüfung der festen Vergleichssequenz und notieren Sie danach nur die rohe Punktzahl pro Modul.",
        )
    else:
        next_session = StudyTip(
            title="Nächste Session",
            action=f"Bearbeiten Sie jetzt das Modul {_module_label(fixed_module)} als nächsten festen Schritt der Vergleichssequenz, ohne zusätzliche Personalisierung.",
        )

    weekly_plan: list[StudyTip] = []
    for offset in range(7):
        module, scope = FIXED_PATH_SEQUENCE[(cycle_index + offset) % len(FIXED_PATH_SEQUENCE)]
        day = offset + 1
        if scope == "full":
            weekly_plan.append(
                StudyTip(
                    title=f"Tag {day}: Gesamtprüfung",
                    action="Bearbeiten Sie eine komplette Goethe-orientierte Gesamtprüfung unter Zeitdruck und dokumentieren Sie anschließend nur Prozentwert und Abschlussnotiz.",
                )
            )
            continue
        weekly_plan.append(
            StudyTip(
                title=f"Tag {day}: {_module_label(module)}",
                action=(
                    f"Trainieren Sie heute nur {_module_label(module)} in der festen Reihenfolge der Vergleichsgruppe. "
                    "Bearbeiten Sie den Modulblock vollständig und notieren Sie Dauer sowie Gesamtprozent."
                ),
            )
        )
    return fixed_module, exam_readiness, next_session, weekly_plan, {
        "mode": "fixed",
        "cycle_index": cycle_index,
        "sequence_labels": sequence_labels,
    }


def get_progress_overview(goal: str) -> ProgressOverviewPayload:
    target_level = _goal_level(goal)
    with connection_scope() as conn:
        due_flashcards = conn.execute("SELECT COUNT(*) FROM cards WHERE due_date <= ?", (today_iso(),)).fetchone()[0]
        exam_attempt_rows = conn.execute(
            """
            SELECT module, percent, created_at
            FROM attempts
            WHERE category = 'exam' AND level = ?
            ORDER BY created_at DESC
            """,
            (target_level,),
        ).fetchall()
        skill_rows = conn.execute(
            """
            SELECT module, AVG(percent) AS average_percent, COUNT(*) AS attempts
            FROM attempts
            WHERE module NOT IN ('diagnostic', 'full')
            GROUP BY module
            ORDER BY average_percent ASC, attempts DESC
            """
        ).fetchall()
        exam_skill_rows = conn.execute(
            """
            SELECT module, AVG(percent) AS average_percent, COUNT(*) AS attempts
            FROM attempts
            WHERE category = 'exam' AND level = ? AND module IN ('lesen', 'hoeren', 'schreiben', 'sprechen')
            GROUP BY module
            ORDER BY average_percent ASC, attempts DESC
            """,
            (target_level,),
        ).fetchall()
        exam_summary = conn.execute(
            "SELECT AVG(percent) AS average_percent, COUNT(*) AS attempts FROM attempts WHERE category = 'exam' AND level = ?",
            (target_level,),
        ).fetchone()
        weak_skills = [
            SkillStat(
                skill=row["module"],
                average_percent=round(float(row["average_percent"] or 0.0), 1),
                attempts=int(row["attempts"]),
            )
            for row in skill_rows[:5]
        ]
        error_rows = conn.execute("SELECT tag, example FROM error_tags ORDER BY created_at DESC").fetchall()
        latest_placement = conn.execute(
            "SELECT result_json FROM placement_sessions WHERE result_json IS NOT NULL ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        active_roadmap = _active_roadmap_summary(conn)

    counter = Counter(row["tag"] for row in error_rows)
    top_errors = [
        build_error_insight(
            tag,
            next((row["example"] for row in error_rows if row["tag"] == tag), tag),
            f"Error recurrente detectado {counter[tag]} veces.",
        )
        for tag, _ in counter.most_common(6)
    ]
    priority_module = None
    priority_module_score = None
    if exam_skill_rows:
        priority_module = str(exam_skill_rows[0]["module"])
        priority_module_score = round(float(exam_skill_rows[0]["average_percent"] or 0.0), 1)

    exam_attempts = int(exam_summary["attempts"] or 0) if exam_summary else 0
    exam_average = round(float(exam_summary["average_percent"] or 0.0), 1) if exam_summary else 0.0
    recommendation_strategy = current_recommendation_strategy()

    latest_placement_level = None
    placement_payload = None
    if latest_placement and latest_placement["result_json"]:
        from ..schemas import PlacementResultPayload

        placement_payload = PlacementResultPayload.model_validate_json(latest_placement["result_json"])
        latest_placement_level = placement_payload.overall_level

    attempt_scores: dict[str, list[float]] = {}
    for row in exam_attempt_rows:
        attempt_scores.setdefault(str(row["module"]), []).append(float(row["percent"]))

    module_probabilities = [
        _build_probability_stat(
            label=_module_label(module),
            module=module,
            scores=attempt_scores.get(module, []),
            note_hint=f"Noch keine Modulprüfung für {_module_label(module)} auf Niveau {target_level}.",
        )
        for module in ("lesen", "hoeren", "schreiben", "sprechen")
    ]

    full_scores = attempt_scores.get("full", [])
    inferred_full_percent = None
    inferred_full_note = ""
    if not full_scores:
        module_averages = [item.average_percent for item in module_probabilities if item.average_percent is not None]
        if module_averages:
            inferred_full_percent = round((sum(module_averages) / len(module_averages)) * 0.7 + (min(module_averages) * 0.3), 1)
            inferred_full_note = (
                f"Geschätzt aus {len(module_averages)}/4 Prüfungsmodulen auf Niveau {target_level}; "
                "unvollständige Modulabdeckung bleibt eine eingeschränkte Datenbasis."
            )

    full_exam_probability = _build_probability_stat(
        label="Gesamtprüfung",
        module="full",
        scores=full_scores,
        inferred_percent=inferred_full_percent,
        note_hint=inferred_full_note,
    )

    if recommendation_strategy == "fixed_path_v1":
        priority_module, exam_readiness, next_session, weekly_plan, strategy_context = _fixed_path_recommendation(
            exam_attempts=exam_attempts,
        )
        recommended_scope = "full" if priority_module is None else "module"
    else:
        recommended_scope, exam_readiness, next_session, weekly_plan, strategy_context = _adaptive_progress_recommendation(
            goal=goal,
            exam_attempts=exam_attempts,
            exam_average=exam_average,
            priority_module=priority_module,
            priority_module_score=priority_module_score,
            top_errors=top_errors,
        )

    exam_readiness = f"{READINESS_NOTE} Zielniveau {target_level}. {exam_readiness}"
    next_action = next_session.action if next_session else exam_readiness
    recommendation_event_id = save_recommendation_event(
        source="progress_overview",
        goal_exam=goal,
        recommended_scope=recommended_scope,
        priority_module=priority_module,
        next_action=next_action,
        context_payload={
            "latest_placement_level": latest_placement_level,
            "exam_attempts": exam_attempts,
            "exam_average": exam_average,
            "full_exam_probability": (
                full_exam_probability.probability_percent
                if full_exam_probability.probability_percent is not None
                else None
            ),
            "recommendation_strategy": recommendation_strategy,
            **strategy_context,
        },
        strategy_label=recommendation_strategy,
    )

    return ProgressOverviewPayload(
        current_goal=goal,
        recommendation_strategy=recommendation_strategy,
        recommendation_event_id=recommendation_event_id,
        streak_days=_compute_streak_safe(),
        due_flashcards=int(due_flashcards),
        weak_skills=weak_skills,
        top_errors=top_errors,
        weekly_plan=weekly_plan,
        full_exam_probability=full_exam_probability,
        module_probabilities=module_probabilities,
        priority_module=priority_module,
        recommended_exam_scope=recommended_scope,
        exam_readiness=exam_readiness,
        next_session=next_session,
        active_roadmap=active_roadmap,
        latest_placement_level=latest_placement_level,
    )


def _compute_streak_safe() -> int:
    with connection_scope() as conn:
        return _streak_days(conn)
