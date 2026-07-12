from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from typing import Any, Iterable, Sequence
from uuid import uuid4

from ..config import (
    DEFAULT_ASSESSMENT_MODE,
    DEFAULT_GOAL_EXAM,
    DEFAULT_RECOMMENDATION_STRATEGY,
    DEFAULT_REVIEW_STRATEGY,
    LOCAL_USER_ID,
)
from ..db import connection_scope
from ..learning_materials import GOAL_EXAM_LABELS, TOPIC_ALIASES, TOPIC_SCENARIOS
from ..schemas import ErrorInsight, StudyTip

LEVEL_ORDER = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
MODULE_LABELS = {
    "lesen": "Lesen",
    "hoeren": "Hören",
    "schreiben": "Schreiben",
    "sprechen": "Sprechen",
    "grammar": "Grammatik",
    "writing": "Schreiben",
    "speaking": "Sprechen",
    "chat": "Interaktion",
    "vocab": "Wortschatz",
    "diagnostic": "Diagnose",
}

ERROR_METADATA = {
    "aufgabenbezug": (
        "Aufgabenbezug",
        "Die Antwort deckt nicht alle geforderten Punkte ab.",
        "Markieren Sie zuerst alle Leitpunkte und arbeiten Sie sie nacheinander ab.",
    ),
    "koharenz": (
        "Kohärenz",
        "Die Ideen sind vorhanden, aber die Verknüpfung ist noch nicht klar genug.",
        "Nutzen Sie Konnektoren wie `zuerst`, `außerdem`, `deshalb` und `abschließend`.",
    ),
    "grammatik": (
        "Grammatik",
        "Es gibt Fehler in Struktur, Form oder Verbflexion.",
        "Formulieren Sie täglich zwei kurze Sätze neu und prüfen Sie Verbposition und Endungen.",
    ),
    "wortstellung": (
        "Wortstellung",
        "Die Position von Verb oder Satzgliedern ist noch instabil.",
        "Wiederholen Sie Verbzweitstellung im Hauptsatz und Verbendstellung im Nebensatz.",
    ),
    "satzzeichen": (
        "Satzzeichen",
        "Die Zeichensetzung erschwert die natürliche Lesbarkeit.",
        "Schließen Sie jede Aussage mit Punkt oder Fragezeichen ab und lesen Sie den Text laut nach.",
    ),
    "wortschatz": (
        "Wortschatz",
        "Es fehlt an lexikalischer Präzision oder es gibt zu viele Wiederholungen.",
        "Lernen Sie 8-10 typische Kollokationen zum Thema und verwenden Sie sie in eigenen Sätzen.",
    ),
    "register": (
        "Register",
        "Der Ton passt noch nicht vollständig zur Aufgabe.",
        "Entscheiden Sie vor dem Schreiben, ob die Aufgabe formal, neutral oder persönlich sein soll, und bleiben Sie dabei.",
    ),
    "interaktion": (
        "Interaktion",
        "Die Antwort kommuniziert, reagiert aber noch nicht ausreichend oder entwickelt den Gedanken zu wenig weiter.",
        "Fügen Sie eine Reaktion, einen Vorschlag und eine kurze Rückfrage hinzu.",
    ),
    "kasus": (
        "Kasus",
        "Es gibt Fehler bei Artikel oder Kasus.",
        "Wiederholen Sie Artikel und Kasus mit kurzen Kontrastbeispielen.",
    ),
    "praepositionen": (
        "Präpositionen",
        "Die gewählte Präposition passt noch nicht.",
        "Lernen Sie Präpositionen immer zusammen mit dem geforderten Kasus und einem Beispielsatz.",
    ),
}

SPANISH_FILLERS = {"pero", "porque", "entonces", "vale", "bueno", "aunque", "ademas", "además"}
ENGLISH_FILLERS = {"because", "actually", "maybe", "thing", "stuff", "really"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_iso() -> str:
    return date.today().isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _normalized_strategy_label(value: str | None, fallback: str) -> str:
    label = str(value or "").strip().lower()
    return label or fallback


def current_recommendation_strategy() -> str:
    try:
        with connection_scope() as conn:
            row = conn.execute(
                "SELECT recommendation_strategy FROM app_settings WHERE user_id = ?",
                (LOCAL_USER_ID,),
            ).fetchone()
    except Exception:
        row = None
    return _normalized_strategy_label(
        row["recommendation_strategy"] if row else DEFAULT_RECOMMENDATION_STRATEGY,
        "adaptive_heuristic_v1",
    )


def current_review_strategy() -> str:
    try:
        with connection_scope() as conn:
            row = conn.execute(
                "SELECT review_strategy FROM app_settings WHERE user_id = ?",
                (LOCAL_USER_ID,),
            ).fetchone()
    except Exception:
        row = None
    return _normalized_strategy_label(
        row["review_strategy"] if row else DEFAULT_REVIEW_STRATEGY,
        "sm2_v1",
    )


def current_assessment_mode() -> str:
    return _normalized_strategy_label(DEFAULT_ASSESSMENT_MODE, "standard_v1")


# Strategy-level tracking stays global; event-level linkage is only added when a
# concrete recommendation event id is explicitly carried into a launched flow.
def resolve_recommendation_attribution(conn: Any, recommendation_event_id: str | None) -> tuple[int, str | None, str | None]:
    normalized_id = str(recommendation_event_id or "").strip()
    if not normalized_id:
        return 0, None, None
    row = conn.execute(
        "SELECT id, strategy_label FROM recommendation_events WHERE id = ?",
        (normalized_id,),
    ).fetchone()
    if not row:
        return 0, None, None
    return 1, row["id"], row["strategy_label"]


def level_rank(level: str) -> int:
    return LEVEL_ORDER.get(str(level).upper(), 0)


def next_level(level: str) -> str:
    order = ["A1", "A2", "B1", "B2", "C1", "C2"]
    try:
        index = order.index(level.upper())
    except ValueError:
        return "A1"
    return order[min(index + 1, len(order) - 1)]


def level_from_percent(percent: float) -> str:
    if percent >= 95:
        return "C2"
    if percent >= 88:
        return "C1"
    if percent >= 76:
        return "B2"
    if percent >= 62:
        return "B1"
    if percent >= 45:
        return "A2"
    return "A1"


def stable_pick(items: Sequence[Any], count: int, seed_key: str) -> list[Any]:
    if count <= 0:
        return []
    hashed = hashlib.sha256(seed_key.encode("utf-8")).hexdigest()
    ordered = sorted(
        enumerate(items),
        key=lambda pair: hashlib.sha256(f"{hashed}:{pair[0]}".encode("utf-8")).hexdigest(),
    )
    return [pair[1] for pair in ordered[: min(count, len(items))]]


def normalize_topic(topic: str | None) -> str:
    if not topic:
        return "arbeit"
    cleaned = re.sub(r"\s+", " ", topic.strip().lower())
    ascii_clean = cleaned.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    for key, value in TOPIC_ALIASES.items():
        if key in cleaned or key in ascii_clean:
            return value
    return "arbeit"


def topic_payload(topic: str | None) -> dict[str, Any]:
    key = normalize_topic(topic)
    return TOPIC_SCENARIOS.get(key, TOPIC_SCENARIOS["arbeit"])


def to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def from_json(value: str) -> Any:
    return json.loads(value) if value else None


def normalize_answer(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def split_words(text: str) -> list[str]:
    return re.findall(r"[A-Za-zÄÖÜäöüß']+", text)


def build_error_insight(tag: str, example: str, description: str | None = None) -> ErrorInsight:
    label, default_description, recommendation = ERROR_METADATA.get(
        tag,
        ("Allgemein", "Hier besteht noch Verbesserungsbedarf.", "Formulieren Sie zu diesem Fehler drei neue Beispielsätze."),
    )
    return ErrorInsight(
        tag=tag,
        label=label,
        description=description or default_description,
        example=example,
        recommendation=recommendation,
    )


def dedupe_errors(errors: Iterable[ErrorInsight]) -> list[ErrorInsight]:
    seen: set[tuple[str, str]] = set()
    unique: list[ErrorInsight] = []
    for error in errors:
        key = (error.tag, error.example)
        if key in seen:
            continue
        seen.add(key)
        unique.append(error)
    return unique


def detect_generic_errors(text: str, *, min_words: int = 0, require_question: bool = False) -> tuple[str, list[ErrorInsight]]:
    errors: list[ErrorInsight] = []
    corrected = re.sub(r"\s+", " ", text.strip())

    if corrected and corrected[-1] not in ".!?":
        corrected = f"{corrected}."
        errors.append(build_error_insight("satzzeichen", text, "Am Ende fehlt ein passendes Satzzeichen."))

    if corrected.startswith("ich "):
        corrected = f"Ich{corrected[3:]}"
        errors.append(build_error_insight("grammatik", text, "Das Pronomen `Ich` muss am Satzanfang großgeschrieben werden."))

    word_count = len(split_words(corrected))
    if min_words and word_count < min_words:
        errors.append(
            build_error_insight(
                "aufgabenbezug",
                text,
                f"Die Produktion ist zu kurz, um die Aufgabe ausreichend zu entwickeln ({word_count} Wörter).",
            )
        )

    lower_words = {word.lower() for word in split_words(corrected)}
    if lower_words & SPANISH_FILLERS or lower_words & ENGLISH_FILLERS:
        errors.append(
            build_error_insight(
                "wortschatz",
                text,
                "Es mischen sich Wörter aus einer anderen Sprache ein; bleiben Sie konsequent im Deutschen.",
            )
        )

    if require_question and "?" not in corrected:
        errors.append(
            build_error_insight(
                "interaktion",
                text,
                "In dieser Aufgabe war mindestens eine direkte Rückfrage oder Reaktion sinnvoll.",
            )
        )

    if "weil" in corrected.lower() and ", weil " not in corrected.lower():
        errors.append(
            build_error_insight(
                "wortstellung",
                text,
                "Bei `weil` sollte der Nebensatz mit Komma abgetrennt und das Verb ans Ende gesetzt werden.",
            )
        )

    return corrected, dedupe_errors(errors)


def compute_open_score(text: str, *, keywords: list[str], max_score: int, min_words: int = 25) -> tuple[float, list[str]]:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned:
        return 0.0, ["Keine verwertbare Antwort abgegeben."]

    word_count = len(split_words(cleaned))
    keyword_hits = sum(1 for keyword in keywords if keyword.lower() in cleaned.lower())
    hints: list[str] = []
    score = 0.0

    if word_count < 3 and keyword_hits == 0:
        return 0.0, ["Die Antwort ist zu kurz oder zu vage, um gewertet zu werden."]

    if word_count >= min_words:
        score += max_score * 0.4
    else:
        hints.append(f"Bauen Sie die Antwort weiter aus: Zielwert mindestens {min_words} Wörter.")
        score += max_score * min(word_count / max(min_words, 1), 1.0) * 0.4

    if keywords:
        coverage = keyword_hits / len(keywords)
        score += max_score * min(coverage, 1.0) * 0.4
        if coverage < 0.6:
            hints.append("Wichtige Leitpunkte oder erwartetes Vokabular fehlen noch.")
    else:
        score += max_score * 0.4

    sentence_count = len([segment for segment in re.split(r"[.!?]+", cleaned) if split_words(segment)])
    if sentence_count >= 2:
        score += max_score * 0.2
    else:
        hints.append("Verwenden Sie mindestens zwei verbundene Sätze, damit die Antwort natürlicher wirkt.")
        score += max_score * 0.1

    return round(min(max_score, score), 2), hints


def objective_match(user_answer: str, expected_answer: str) -> tuple[float, str]:
    normalized_user = normalize_answer(user_answer)
    normalized_expected = normalize_answer(expected_answer)
    if normalized_user == normalized_expected:
        return 1.0, "Richtig."
    if normalized_user and normalized_expected.startswith(normalized_user):
        return 0.5, "Teilweise richtig, aber noch nicht präzise genug."
    return 0.0, "Die Antwort stimmt nicht mit der erwarteten Lösung überein."


def _goal_label(goal_exam: str | None) -> str:
    exam_goal = (goal_exam or DEFAULT_GOAL_EXAM).lower()
    return GOAL_EXAM_LABELS.get(exam_goal, exam_goal.replace("_", " ").upper())


def _module_label(module: str | None) -> str:
    if not module:
        return "Gesamtprüfung"
    return MODULE_LABELS.get(module, module.title())


def build_study_plan(
    tags: list[str],
    goal_exam: str | None = None,
    *,
    days: int = 7,
    priority_module: str | None = None,
    recommended_scope: str = "full",
) -> list[StudyTip]:
    exam_goal = goal_exam or DEFAULT_GOAL_EXAM
    exam_label = _goal_label(exam_goal)
    unique_tags = list(dict.fromkeys(tags))[:4] or ["wortschatz", "grammatik"]
    plan: list[StudyTip] = []

    if priority_module:
        scope_action = (
            f"Starten Sie mit einer vollständigen {exam_label}-Gesamtprüfung und beobachten Sie besonders das Modul {_module_label(priority_module)}."
            if recommended_scope == "full"
            else f"Starten Sie mit 25 bis 35 Minuten gezieltem Modultraining in {_module_label(priority_module)} im Stil von {exam_label}."
        )
        plan.append(
            StudyTip(
                title="Tag 1: Prüfungspriorität",
                action=f"{scope_action} Halten Sie danach drei konkrete Fehler oder Engstellen schriftlich fest.",
            )
        )

    for tag in unique_tags:
        label, _, recommendation = ERROR_METADATA.get(tag, ("Allgemein", "", "Arbeiten Sie 15 Minuten gezielt an diesem Bereich."))
        plan.append(
            StudyTip(
                title=f"Tag {len(plan) + 1}: {label}",
                action=f"{recommendation} Schließen Sie mit 10 Minuten Training im Stil von {exam_label} ab.",
            )
        )

    plan.append(
        StudyTip(
            title=f"Tag {len(plan) + 1}: Zeittraining",
            action=(
                f"Bearbeiten Sie eine kompakte {exam_label}-Simulation unter Zeitdruck und ohne Hilfsmittel."
                if recommended_scope == "full"
                else f"Bearbeiten Sie ein einzelnes Modul unter Zeitdruck und halten Sie den offiziellen Goethe-Rahmen exakt ein."
            ),
        )
    )
    plan.append(
        StudyTip(
            title=f"Tag {len(plan) + 1}: Fehlerprotokoll",
            action="Ordnen Sie Ihre wiederkehrenden Fehler in drei Gruppen: Struktur, Wortschatz und Aufgabenbezug. Wiederholen Sie danach nur die schwächste Gruppe.",
        )
    )

    while len(plan) < days:
        plan.append(
            StudyTip(
                title=f"Tag {len(plan) + 1}: Gemischte Wiederholung",
                action=f"Kombinieren Sie 10 Minuten Karteikarten mit 15 Minuten Training im Stil von {exam_label} und schließen Sie mit einer kurzen Selbstkontrolle ab.",
            )
        )
    return plan[:days]


def save_exercise(
    *,
    exercise_id: str,
    category: str,
    module: str,
    level: str,
    title: str,
    prompt_payload: dict[str, Any],
    answer_payload: dict[str, Any],
    criteria_payload: list[str],
    meta_payload: dict[str, Any],
) -> None:
    with connection_scope() as conn:
        conn.execute(
            """
            INSERT INTO exercises (
                id, category, module, level, title, prompt_json, answer_json, criteria_json, meta_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exercise_id,
                category,
                module,
                level,
                title,
                to_json(prompt_payload),
                to_json(answer_payload),
                to_json(criteria_payload),
                to_json(meta_payload),
                utc_now_iso(),
            ),
        )


def get_exercise(exercise_id: str) -> dict[str, Any] | None:
    with connection_scope() as conn:
        row = conn.execute("SELECT * FROM exercises WHERE id = ?", (exercise_id,)).fetchone()
    if not row:
        return None
    payload = dict(row)
    payload["prompt_json"] = from_json(payload["prompt_json"])
    payload["answer_json"] = from_json(payload["answer_json"])
    payload["criteria_json"] = from_json(payload["criteria_json"])
    payload["meta_json"] = from_json(payload["meta_json"])
    return payload


def save_attempt(
    *,
    exercise_id: str,
    category: str,
    module: str,
    level: str,
    user_answers: dict[str, Any],
    score: float,
    max_score: float,
    percent: float,
    feedback_payload: dict[str, Any],
    corrected_payload: dict[str, Any],
    error_tags_payload: list[dict[str, Any]],
    recommendation_strategy: str | None = None,
    review_strategy: str | None = None,
    assessment_mode: str | None = None,
    recommendation_event_id: str | None = None,
) -> str:
    attempt_id = make_id("attempt")
    created_at = utc_now_iso()
    recommendation_label = _normalized_strategy_label(
        recommendation_strategy,
        current_recommendation_strategy(),
    )
    review_label = _normalized_strategy_label(
        review_strategy,
        current_review_strategy(),
    )
    assessment_label = _normalized_strategy_label(
        assessment_mode,
        current_assessment_mode(),
    )
    with connection_scope() as conn:
        launched_from_recommendation, linked_recommendation_event_id, linked_recommendation_strategy = resolve_recommendation_attribution(
            conn,
            recommendation_event_id,
        )
        conn.execute(
            """
            INSERT INTO attempts (
                id, exercise_id, category, module, level, user_answers_json, score, max_score, percent,
                feedback_json, corrected_json, error_tags_json, recommendation_strategy,
                review_strategy, assessment_mode, launched_from_recommendation, recommendation_event_id,
                linked_recommendation_strategy, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt_id,
                exercise_id,
                category,
                module,
                level,
                to_json(user_answers),
                score,
                max_score,
                percent,
                to_json(feedback_payload),
                to_json(corrected_payload),
                to_json(error_tags_payload),
                recommendation_label,
                review_label,
                assessment_label,
                launched_from_recommendation,
                linked_recommendation_event_id,
                linked_recommendation_strategy,
                created_at,
            ),
        )
        for tag_payload in error_tags_payload:
            conn.execute(
                """
                INSERT INTO error_tags (attempt_id, category, skill, tag, example, weight, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    category,
                    module,
                    tag_payload["tag"],
                    tag_payload["example"],
                    1,
                    created_at,
                ),
            )
    return attempt_id


def save_recommendation_event(
    *,
    source: str,
    goal_exam: str,
    next_action: str,
    recommended_scope: str | None = None,
    priority_module: str | None = None,
    context_payload: dict[str, Any] | None = None,
    strategy_label: str | None = None,
) -> str:
    event_id = make_id("reco")
    created_at = utc_now_iso()
    with connection_scope() as conn:
        conn.execute(
            """
            INSERT INTO recommendation_events (
                id, source, strategy_label, goal_exam, recommended_scope, priority_module,
                next_action, context_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                source,
                _normalized_strategy_label(strategy_label, current_recommendation_strategy()),
                goal_exam,
                recommended_scope,
                priority_module,
                next_action,
                to_json(context_payload or {}),
                created_at,
            ),
        )
    return event_id


def ensure_local_user() -> None:
    created_at = utc_now_iso()
    with connection_scope() as conn:
        row = conn.execute("SELECT id FROM app_users WHERE id = ?", (LOCAL_USER_ID,)).fetchone()
        if row:
            conn.execute(
                "UPDATE app_users SET updated_at = ?, goal_exam = ? WHERE id = ?",
                (created_at, DEFAULT_GOAL_EXAM, LOCAL_USER_ID),
            )
            return
        conn.execute(
            """
            INSERT INTO app_users (id, username, goal_exam, goal_level, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (LOCAL_USER_ID, "local", DEFAULT_GOAL_EXAM, "B2", created_at, created_at),
        )
