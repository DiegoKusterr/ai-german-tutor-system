from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..db import connection_scope
from ..goethe_mock_bank import GOETHE_MOCK_SCENARIOS
from ..goethe_official import GOETHE_OFFICIAL_EXAMS
from ..grammar_content_advanced import GRAMMAR_CURRICULUM_ADVANCED
from ..grammar_content_base import GRAMMAR_CURRICULUM_BASE
from ..grammar_content_reference import GRAMMAR_CURRICULUM_REFERENCE
from ..learning_materials import (
    EXAM_CRITERIA,
    SPEAKING_SCENARIOS,
    TOPIC_ALIASES,
    VOCAB_BANK,
    WRITING_TASKS,
)
from ..schemas import (
    EvaluationPayload,
    ExamGenerateRequest,
    ExamPart,
    ExamPayload,
    ExamSubmitRequest,
    ExerciseItem,
    ExerciseResultItem,
    GrammarGenerateRequest,
    GrammarPayload,
    GrammarSubmitRequest,
    GrammarTheoryPayload,
    GrammarTopicSummary,
    OfficialExamModule,
    OfficialExamPayload,
    OfficialExamRequest,
    OfficialExamResource,
    OfficialPracticeSet,
    RubricScore,
    SectionScore,
    SpeakingFeedbackRequest,
    SpeakingSimulationPayload,
    SpeakingSimulateRequest,
    SpeakingTurnPayload,
    VocabFromTopicRequest,
    VocabItem,
    VocabPayload,
    WritingGradePayload,
    WritingGradeRequest,
    WritingPromptPayload,
    WritingPromptRequest,
)
from .common import (
    build_error_insight,
    build_study_plan,
    compute_open_score,
    dedupe_errors,
    detect_generic_errors,
    ensure_local_user,
    get_exercise,
    make_id,
    objective_match,
    save_attempt,
    save_exercise,
    stable_pick,
    split_words,
    to_json,
    topic_payload,
    utc_now_iso,
)
from .exam_mock_generation import generate_goethe_mock_exam
from .mock_telemetry import save_mock_generation_run

GRAMMAR_LIBRARY = {
    **GRAMMAR_CURRICULUM_BASE,
    **GRAMMAR_CURRICULUM_ADVANCED,
    **GRAMMAR_CURRICULUM_REFERENCE,
}

OFFICIAL_RESOURCE_HOSTS = {"www.goethe.de", "goethe.de"}
OFFICIAL_RESOURCE_MAX_BYTES = 30 * 1024 * 1024

_ASCII_TRANSLATION = str.maketrans(
    {
        "Ä": "Ae",
        "Ö": "Oe",
        "Ü": "Ue",
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
    }
)


def _as_ascii_key(value: str) -> str:
    normalized = value.translate(_ASCII_TRANSLATION)
    return normalized.lower()


def _module_part_points(module_def: dict[str, Any]) -> dict[str, int]:
    parts = list(module_def["parts"])
    total_slots = sum(int(part.get("item_count") or 1) for part in parts)
    point_plan = _distribute_points(int(module_def["scoring"]["max_points"]), total_slots)
    mapping: dict[str, int] = {}
    point_index = 0
    for part in parts:
        part_slots = int(part.get("item_count") or 1)
        mapping[str(part["key"])] = sum(point_plan[point_index : point_index + part_slots])
        point_index += part_slots
    return mapping


def _official_module_parts(module_def: dict[str, Any]) -> list[ExamPart]:
    point_map = _module_part_points(module_def)
    return [
        ExamPart(
            **{
                **part,
                "points": point_map.get(str(part["key"])),
            }
        )
        for part in module_def["parts"]
    ]


OPEN_RESPONSE_STOPWORDS = {
    "aber",
    "alle",
    "alles",
    "also",
    "auch",
    "aus",
    "bei",
    "bin",
    "bist",
    "damit",
    "dann",
    "dass",
    "dein",
    "dem",
    "den",
    "der",
    "des",
    "die",
    "doch",
    "dort",
    "eine",
    "einem",
    "einen",
    "einer",
    "einfach",
    "einige",
    "er",
    "es",
    "fuer",
    "hat",
    "habe",
    "haben",
    "hier",
    "ich",
    "ihm",
    "ihn",
    "im",
    "in",
    "ist",
    "ja",
    "kein",
    "keine",
    "man",
    "mit",
    "nach",
    "nicht",
    "noch",
    "oder",
    "sehr",
    "sein",
    "sich",
    "sie",
    "sind",
    "und",
    "uns",
    "vom",
    "von",
    "war",
    "was",
    "weil",
    "wenn",
    "wie",
    "wir",
    "wird",
    "zu",
    "zum",
    "zur",
}

OPEN_NONANSWER_MARKERS = {
    "ich weiss nicht",
    "ich weis nicht",
    "ich weiß nicht",
    "keine ahnung",
    "kein plan",
    "nichts",
    "leer",
    "skip",
    "idk",
    "weiss ich nicht",
    "weiß ich nicht",
}

OPEN_ARGUMENT_MARKERS = {
    "meiner meinung",
    "ich denke",
    "ich finde",
    "aus meiner sicht",
    "einerseits",
    "andererseits",
    "deshalb",
    "daher",
    "abschliessend",
    "abschließend",
    "zum schluss",
    "insgesamt",
}

OPEN_FORMAL_MARKERS = {
    "sehr geehrte",
    "guten tag",
    "mit freundlichen gruessen",
    "mit freundlichen grüßen",
    "freundliche gruesse",
    "freundliche grüße",
}

OPEN_INTERACTION_MARKERS = {
    "?",
    "was meinst",
    "wie siehst",
    "wie waere",
    "wie wäre",
    "einverstanden",
    "koennten wir",
    "könnten wir",
    "sollen wir",
    "ich schlage vor",
    "wenn sie",
    "lassen sie uns",
    "darauf wuerde ich",
    "darauf wurde ich",
    "darf ich",
}

OPEN_DISCOURSE_MARKERS = {
    "zunaechst",
    "zuerst",
    "erstens",
    "zweitens",
    "darueber hinaus",
    "daruber hinaus",
    "ferner",
    "zugleich",
    "allerdings",
    "dennoch",
    "trotzdem",
    "folglich",
    "deshalb",
    "daher",
    "somit",
    "insgesamt",
    "abschliessend",
    "zusammenfassend",
    "zum schluss",
}

OPEN_PRESENTATION_MARKERS = {
    "ich moechte zunaechst",
    "ich moechte zuerst",
    "zunaechst",
    "zuerst",
    "erstens",
    "zweitens",
    "im ersten teil",
    "anschliessend",
    "abschliessend",
    "zusammenfassend",
    "zum schluss",
}

OPEN_COUNTERARGUMENT_MARKERS = {
    "einerseits",
    "andererseits",
    "gleichzeitig",
    "allerdings",
    "dennoch",
    "trotzdem",
    "ich verstehe",
    "ich verstehe den einwand",
    "du hast recht",
    "dem wuerde ich",
    "dem wurde ich",
    "ich sehe das anders",
    "ein gegenargument",
    "anderes argument",
    "auf der anderen seite",
}

OPEN_LEVEL_POLICY = {
    "A1": {"task_floor": 0.32, "length_floor": 0.5, "structure_floor": 0.28, "register_floor": 0.32, "language_floor": 0.42, "precision_floor": 0.12},
    "A2": {"task_floor": 0.38, "length_floor": 0.56, "structure_floor": 0.34, "register_floor": 0.38, "language_floor": 0.48, "precision_floor": 0.16},
    "B1": {"task_floor": 0.46, "length_floor": 0.64, "structure_floor": 0.42, "register_floor": 0.46, "language_floor": 0.54, "precision_floor": 0.2},
    "B2": {"task_floor": 0.56, "length_floor": 0.78, "structure_floor": 0.54, "register_floor": 0.56, "language_floor": 0.6, "precision_floor": 0.28},
    "C1": {"task_floor": 0.64, "length_floor": 0.86, "structure_floor": 0.64, "register_floor": 0.64, "language_floor": 0.66, "precision_floor": 0.34},
    "C2": {"task_floor": 0.7, "length_floor": 0.9, "structure_floor": 0.72, "register_floor": 0.7, "language_floor": 0.72, "precision_floor": 0.4},
}


def _gkey(focus: str) -> str:
    cleaned = _as_ascii_key(focus)
    if cleaned in GRAMMAR_LIBRARY:
        return cleaned
    for key, payload in GRAMMAR_LIBRARY.items():
        haystack = " ".join([key, payload["label"], *payload["related_topics"]]).lower()
        if cleaned in _as_ascii_key(haystack):
            return key
    return "satzbau_verbzweitstellung"


def get_grammar_catalog() -> list[GrammarTopicSummary]:
    return sorted(
        [
            GrammarTopicSummary(
                key=key,
                label=payload["label"],
                level=payload["level"],
                category=payload["category"],
                summary=payload["summary"],
            )
            for key, payload in GRAMMAR_LIBRARY.items()
        ],
        key=lambda item: (item.level, item.category, item.label),
    )


def get_grammar_theory(topic_key: str) -> GrammarTheoryPayload:
    payload = GRAMMAR_LIBRARY.get(topic_key)
    if not payload:
        raise ValueError("Grammatikthema nicht gefunden.")
    return GrammarTheoryPayload(
        key=topic_key,
        label=payload["label"],
        level=payload["level"],
        category=payload["category"],
        summary=payload["summary"],
        when_to_study=payload["when_to_study"],
        core_rules=list(payload["core_rules"]),
        deep_dive=list(payload["deep_dive"]),
        exceptions=list(payload["exceptions"]),
        examples=list(payload["examples"]),
        common_mistakes=list(payload["common_mistakes"]),
        memory_hook=payload["memory_hook"],
        related_topics=list(payload["related_topics"]),
        references=list(payload["references"]),
    )


def _grammar_items(topic_key: str, kind: str, count: int) -> list[ExerciseItem]:
    theory = GRAMMAR_LIBRARY[topic_key]
    examples = theory["examples"] or [theory["summary"]]
    items: list[ExerciseItem] = []
    for idx in range(count):
        example = examples[idx % len(examples)]
        tokens = example.split()
        prompt = example
        answer = example
        item_type = "open"
        options: list[str] = []
        if kind in {"fill_blank", "case_choice", "multiple_choice"} and len(tokens) >= 3:
            answer = tokens[min(1, len(tokens) - 1)]
            masked = tokens[:]
            masked[min(1, len(tokens) - 1)] = "___"
            prompt = " ".join(masked)
            item_type = "mcq" if kind == "multiple_choice" else "fill_blank"
            if item_type == "mcq":
                options = [answer, "weil", "mit", "nicht"]
        elif kind == "reorder":
            item_type = "reorder"
            prompt = " | ".join(reversed(tokens))
        elif kind == "transformation":
            prompt = f"Formulieren Sie korrekt um: {example}"
        items.append(
            ExerciseItem(
                id=f"{topic_key}_{idx + 1}",
                prompt=prompt,
                item_type=item_type,
                options=options,
                answer=answer,
                explanation=theory["core_rules"][0],
                points=1,
                focus_tag=topic_key,
            )
        )
    return items


def _exercise_recommendation_event_id(exercise: dict[str, Any]) -> str | None:
    meta_payload = exercise.get("meta_json") or {}
    recommendation_event_id = str(meta_payload.get("recommendation_event_id") or "").strip()
    return recommendation_event_id or None


def generate_grammar(req: GrammarGenerateRequest) -> GrammarPayload:
    ensure_local_user()
    topic_key = _gkey(req.focus)
    theory = get_grammar_theory(topic_key)
    payload = GrammarPayload(
        exercise_id=make_id("grammar"),
        topic_key=topic_key,
        topic_level=theory.level,
        level=req.level,
        focus=req.focus,
        exercise_type=req.exercise_type,
        title=f"{theory.label} · Theorie + Training",
        instructions="Lesen Sie zuerst die Theorie aufmerksam. Lösen Sie die Aufgaben danach ohne Hilfsmittel und prüfen Sie bewusst Regel, Form und Satzstellung.",
        theory=theory,
        items=_grammar_items(topic_key, req.exercise_type, req.count),
        recommended_review=[
            "Wiederholen Sie morgen nur die falschen oder unsicheren Formen.",
            "Schreiben Sie drei eigene Beispielsätze mit derselben Struktur.",
            "Überführen Sie typische Fehler direkt in Karteikarten.",
        ],
    )
    save_exercise(
        exercise_id=payload.exercise_id,
        category="grammar",
        module=topic_key,
        level=req.level,
        title=payload.title,
        prompt_payload=payload.model_dump(),
        answer_payload={"items": [item.model_dump() for item in payload.items]},
        criteria_payload=payload.theory.core_rules,
        meta_payload={
            "topic_level": theory.level,
            "recommendation_event_id": req.recommendation_event_id,
        },
    )
    return payload


def submit_grammar(req: GrammarSubmitRequest) -> EvaluationPayload:
    exercise = get_exercise(req.exercise_id)
    if not exercise:
        raise ValueError("Grammatikübung nicht gefunden.")
    items = [ExerciseItem.model_validate(item) for item in exercise["prompt_json"]["items"]]
    results: list[ExerciseResultItem] = []
    errors: list[Any] = []
    score = 0.0
    max_score = 0.0
    for item in items:
        user_answer = req.answers.get(item.id, "").strip()
        max_score += item.points
        if item.item_type in {"mcq", "fill_blank", "short", "reorder"}:
            ratio, feedback = objective_match(user_answer, item.answer)
            item_score = ratio * item.points
            corrected = item.answer if ratio < 1 else None
        else:
            item_score, hints = compute_open_score(user_answer, keywords=item.keywords, max_score=item.points, min_words=8)
            feedback = " ".join(hints) if hints else "Die Antwort ist für diese Aufgabe gut aufgebaut."
            corrected = user_answer
        score += item_score
        item_errors = [] if item_score >= item.points else [build_error_insight("grammatik", item.prompt)]
        errors.extend(item_errors)
        results.append(
            ExerciseResultItem(
                item_id=item.id,
                prompt=item.prompt,
                user_answer=user_answer,
                expected_answer=item.answer,
                score=round(item_score, 2),
                max_score=item.points,
                feedback=feedback,
                corrected_version=corrected,
                error_tags=item_errors,
            )
        )
    percent = round(score / max_score * 100, 1) if max_score else 0.0
    attempt_id = save_attempt(
        exercise_id=req.exercise_id,
        category="grammar",
        module=exercise["module"],
        level=exercise["level"],
        user_answers=req.answers,
        score=score,
        max_score=max_score,
        percent=percent,
        feedback_payload={"results": [result.model_dump() for result in results]},
        corrected_payload={"results": [result.corrected_version for result in results]},
        error_tags_payload=[error.model_dump() for error in errors],
        recommendation_event_id=_exercise_recommendation_event_id(exercise),
    )
    return EvaluationPayload(
        attempt_id=attempt_id,
        exercise_id=req.exercise_id,
        title=exercise["title"],
        category="grammar",
        module=exercise["module"],
        level=exercise["level"],
        score=round(score, 2),
        max_score=max_score,
        percent=percent,
        summary="Sehr solide Kontrolle der Struktur." if percent >= 80 else "Die Theorie sollte noch einmal gezielt mit den konkreten Fehlern wiederholt werden.",
        recurring_errors=errors[:6],
        what_to_improve=[error.recommendation for error in errors[:4]],
        mini_drills=[
            "Schreiben Sie drei neue Sätze mit derselben Regel.",
            "Wiederholen Sie morgen nur die falschen oder unsicheren Aufgaben.",
        ],
        study_plan=build_study_plan([error.tag for error in errors], "goethe_b2"),
        results=results,
        official_alignment="Kuratiertes Grammatiktraining mit Theorie- und Anwendungsmodus.",
        pass_threshold=60.0,
    )


def _official(level: str, scope: str, module: str) -> OfficialExamPayload:
    exam = GOETHE_OFFICIAL_EXAMS[level]
    selected = ["lesen", "hoeren", "schreiben", "sprechen"] if scope == "full" else [module]
    modules = [
        OfficialExamModule(
            key=exam["modules"][item]["key"],
            label=exam["modules"][item]["label"],
            duration_minutes=exam["modules"][item]["duration_minutes"],
            prep_minutes=exam["modules"][item]["prep_minutes"],
            structure=list(exam["modules"][item]["structure"]),
            parts=_official_module_parts(exam["modules"][item]),
            scoring=exam["modules"][item]["scoring"],
        )
        for item in selected
    ]
    return OfficialExamPayload(
        institution="goethe",
        level=level,
        scope=scope,
        selected_module=module if scope == "module" else None,
        title=exam["title"],
        is_modular=bool(exam["is_modular"]),
        official_version=str(exam["official_version"]),
        pass_rule=str(exam["pass_rule"]),
        official_note=exam["official_note"],
        page_url=exam["page_url"],
        official_page_url=exam["page_url"],
        practice_page_url=exam.get("practice_page_url"),
        resources=[OfficialExamResource(**resource) for resource in exam["resources"]],
        practice_sets=[
            OfficialPracticeSet(
                key=practice_set["key"],
                label=practice_set["label"],
                audience=practice_set["audience"],
                description=str(practice_set.get("description", "")),
                default_resource_type=str(practice_set.get("default_resource_type", "digital")),
                resources=[OfficialExamResource(**resource) for resource in practice_set.get("resources", [])],
            )
            for practice_set in exam.get("practice_sets", [])
        ],
        modules=modules,
        mock_calibration=list(exam.get("mock_calibration", [])),
        notes=list(exam["notes"]),
    )


def get_official_exam(req: OfficialExamRequest) -> OfficialExamPayload:
    return _official(req.level, req.scope, req.module)


def get_official_resource(url: str) -> tuple[bytes, str]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc not in OFFICIAL_RESOURCE_HOSTS:
        raise ValueError("Nur offizielle Goethe-PDFs duerfen ueber den App-Proxy geladen werden.")
    if not parsed.path.lower().endswith(".pdf"):
        raise ValueError("Der interne Viewer-Proxydienst unterstuetzt nur offizielle PDF-Ressourcen.")
    request = Request(
        url,
        headers={
            "User-Agent": "Deutsch-Lernstudio/1.0 (+official-goethe-pdf-proxy)",
            "Accept": "application/pdf,*/*",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            content_type = response.headers.get_content_type() or "application/pdf"
            if content_type != "application/pdf":
                raise ValueError("Die angeforderte Ressource wurde nicht als PDF geliefert.")
            payload = response.read(OFFICIAL_RESOURCE_MAX_BYTES + 1)
    except (HTTPError, URLError) as exc:
        raise ValueError("Das offizielle PDF konnte gerade nicht geladen werden.") from exc
    if len(payload) > OFFICIAL_RESOURCE_MAX_BYTES:
        raise ValueError("Das offizielle PDF ist fuer den integrierten Viewer zu gross.")
    return payload, content_type


def _module_def(level: str, module: str) -> dict[str, Any]:
    return GOETHE_OFFICIAL_EXAMS[level]["modules"][module]


def _expand_scenario_pool(pool: list[dict[str, Any]], count: int, seed_key: str) -> list[dict[str, Any]]:
    if count <= 0:
        return []
    if not pool:
        fallback = topic_payload(None)
        return [dict(fallback) for _ in range(count)]
    result: list[dict[str, Any]] = []
    batch_index = 0
    while len(result) < count:
        ordered = stable_pick(pool, len(pool), f"{seed_key}:{batch_index}")
        if not ordered:
            break
        result.extend(dict(item) for item in ordered)
        batch_index += 1
    if not result:
        fallback = topic_payload(None)
        return [dict(fallback) for _ in range(count)]
    return result[:count]


def _part_scenarios(level: str, module: str, part_count: int, topic: str | None, variant_seed: str | None) -> list[dict[str, Any]]:
    if topic:
        fixed = topic_payload(topic)
        return [dict(fixed) for _ in range(part_count)]
    pool = [dict(item) for item in GOETHE_MOCK_SCENARIOS.get(level, [])]
    seed_key = variant_seed or f"{level}:{module}:default"
    return _expand_scenario_pool(pool, part_count, f"{level}:{module}:{seed_key}")


def _distribute_points(total_points: int, slots: int) -> list[int]:
    if slots <= 0:
        return []
    base, remainder = divmod(total_points, slots)
    return [base + (1 if idx < remainder else 0) for idx in range(slots)]


def _objective_item(
    *,
    level: str,
    module: str,
    part: dict[str, Any],
    scenario: dict[str, Any],
    item_number: int,
    points: int,
) -> ExerciseItem:
    options = _response_options(part, scenario)
    answer = options[item_number % len(options)] if options else "Richtig"
    item_type = "true_false" if str(part.get("item_kind")) in {"true_false", "yes_no"} else "mcq"
    return ExerciseItem(
        id=f"{part['key']}_{item_number}",
        section=module,
        section_title=part["title"],
        prompt=_objective_prompt(part, item_number + 1),
        support_text=_support_text(level, module, part, scenario, item_number + 1),
        item_type=item_type,
        options=options,
        answer=answer,
        explanation=part["instructions"],
        points=points,
        focus_tag=module,
    )


def _open_keywords(scenario: dict[str, Any]) -> list[str]:
    return ["Problem", "Lösung", "Vorschlag", *scenario["keywords"][:2]]


def _open_min_words(level: str, part: dict[str, Any]) -> int:
    if part.get("min_words"):
        return int(part["min_words"])
    if part.get("expected_words"):
        return max(25, int(part["expected_words"]) // 2)
    defaults = {"A1": 25, "A2": 35, "B1": 60, "B2": 90, "C1": 120, "C2": 160}
    return defaults.get(level, 50)


def _open_item(
    *,
    level: str,
    module: str,
    part: dict[str, Any],
    scenario: dict[str, Any],
    points: int,
) -> ExerciseItem:
    label = "Schreiben" if module == "schreiben" else "Sprechen"
    return ExerciseItem(
        id=part["key"],
        section=module,
        section_title=part["title"],
        prompt=f"{part['title']}: {part['instructions']}",
        support_text=_open_support_text(module, part, scenario),
        item_type="open",
        answer=f"freie {label.lower()} Bearbeitung",
        explanation=f"Bewertet werden die für {label} veröffentlichten Goethe-Kriterien dieses Moduls.",
        points=points,
        keywords=_open_keywords(scenario),
        min_words=_open_min_words(level, part),
        focus_tag=module,
    )


def _response_options(part: dict[str, Any], scenario: dict[str, Any]) -> list[str]:
    item_kind = str(part.get("item_kind", "mcq3"))
    if item_kind == "true_false":
        return ["Richtig", "Falsch"]
    if item_kind == "yes_no":
        return ["Ja", "Nein"]
    if item_kind in {"matching_letters", "matching_speakers", "matching_headings", "matching_locations", "matching_words"}:
        return [str(option) for option in part.get("choice_options", [])]
    option_count = 4 if item_kind == "mcq4" else 3
    return [chr(ord("a") + idx) for idx in range(option_count)]


def _choice_legend(part: dict[str, Any], scenario: dict[str, Any]) -> list[str]:
    options = [str(option) for option in part.get("choice_options", [])]
    title_lower = f"{part['key']} {part['title']} {part['instructions']}".lower()
    if not options and str(part.get("item_kind", "mcq3")) in {"mcq3", "mcq4"}:
        options = _response_options(part, scenario)
        variants = [
            f"{scenario['person']} verfolgt vor allem das Ziel, {scenario['goal']}.",
            f"Im Mittelpunkt steht das Problem, dass {scenario['issue']}.",
            f"Die Kernaussage ist der Vorschlag: {scenario['solution']}.",
            f"Entscheidend ist der Kontext {scenario['setting']} um {scenario['time']}.",
        ]
        return [f"{option}) {variants[idx]}" for idx, option in enumerate(options)]
    if not options:
        return []
    if "ueberschrift" in title_lower or "überschrift" in title_lower:
        headings = [
            "Nutzen im Alltag",
            "Kritik am bisherigen System",
            "Ein überraschendes Beispiel",
            "Praktische Lösungsvorschläge",
            "Vorteile für die Zukunft",
            "Risiken und Nebenwirkungen",
            "Keine Überschrift passt",
        ]
        return [f"{option}) {headings[idx % len(headings)]}" for idx, option in enumerate(options)]
    if "sprecher" in title_lower or "diskussion" in title_lower or "gespräch" in title_lower:
        return [f"{option}) Sprecher {idx + 1} mit klar eigener Position" for idx, option in enumerate(options)]
    if "angebot" in title_lower or "anzeig" in title_lower:
        return [f"{option}) Angebot {idx + 1} mit eigenem Schwerpunkt" for idx, option in enumerate(options)]
    if "ordnung" in title_lower or "anweisung" in title_lower or "abschnitt" in title_lower:
        return [f"{option}) Abschnitt {idx + 1} der Regel- oder Informationstexte" for idx, option in enumerate(options)]
    if "informationstafel" in title_lower or "stock" in title_lower:
        return [f"{option}) passender Ort oder Bereich" for option in options]
    if str(part.get("item_kind")) == "matching_words":
        return [f"{option}) diese Position trifft auf die Aussage zu" for option in options]
    return [f"{option}) Passende Zuordnung" if option == "0" else f"{option}) Text/Person/Abschnitt {idx + 1}" for idx, option in enumerate(options)]


def _source_frame(level: str, module: str, part: dict[str, Any], scenario: dict[str, Any], item_number: int) -> list[str]:
    title_lower = f"{part['key']} {part['title']} {part['instructions']}".lower()
    if module == "lesen":
        if "korrespondenz" in title_lower or "e-mail" in title_lower or "mitteilung" in title_lower:
            return [
                f"Textbasis {item_number}: Nachricht von {scenario['person']} aus {scenario['setting']}.",
                f"Anliegen: {scenario['goal']}.",
                f"Problemhinweis: {scenario['issue']}.",
            ]
        if "standpunkte" in title_lower or "positionen" in title_lower or "meinungen" in title_lower:
            return [
                f"Textbasis {item_number}: mehrere kurze Aussagen zum Thema {scenario['title']}.",
                f"Person a betont den Nutzen von {scenario['goal']}.",
                f"Person b problematisiert, dass {scenario['issue']}.",
                f"Person c unterstützt als Lösung {scenario['solution']}.",
            ]
        if "lückentext" in title_lower or "textrekonstruktion" in title_lower:
            return [
                f"Textbasis {item_number}: zusammenhängender Artikel mit Lücken zu {scenario['title']}.",
                f"Der Text schildert die Situation {scenario['setting']} und entwickelt mehrere Argumentationsschritte.",
            ]
        if "kommentar" in title_lower or "artikel" in title_lower or "presse" in title_lower:
            return [
                f"Textbasis {item_number}: Presse- oder Sachtext zu {scenario['title']}.",
                f"Zentrale These: {scenario['goal']}.",
                f"Gegenposition oder Schwierigkeit: {scenario['issue']}.",
            ]
        if "angebot" in title_lower or "anzeig" in title_lower or "orientierung" in title_lower:
            return [
                f"Textbasis {item_number}: mehrere kurze Angebote, Hinweise oder Anzeigen.",
                f"Gesucht wird die beste Lösung für {scenario['person']} mit Blick auf {scenario['goal']}.",
            ]
        return [
            f"Textbasis {item_number}: {part['title']}.",
            f"Rahmenthema: {scenario['title']} in {scenario['setting']}.",
        ]
    if "kurze texte" in title_lower or "kurze gespräche" in title_lower or "radiosendungen" in title_lower:
        return [
            f"Transkriptbasis {item_number}: kurzer Hörtext {item_number} zu {scenario['title']}.",
            f"Sprecherin oder Sprecher erwähnt das Ziel {scenario['goal']}.",
            f"Der kritische Punkt ist: {scenario['issue']}.",
        ]
    if "interview" in title_lower:
        return [
            f"Transkriptbasis {item_number}: Interview über {scenario['title']}.",
            f"Die interviewte Person erklärt ihren Standpunkt zu {scenario['goal']}.",
            f"Im Verlauf wird auch das Problem {scenario['issue']} angesprochen.",
        ]
    if "podcast" in title_lower or "vortrag" in title_lower:
        return [
            f"Transkriptbasis {item_number}: zusammenhängender Beitrag oder Vortrag zum Thema {scenario['title']}.",
            f"Der Beitrag ordnet die Situation {scenario['setting']} ein und endet mit {scenario['solution']}.",
        ]
    if "diskussion" in title_lower or "mehreren personen" in title_lower or "gespräch" in title_lower:
        return [
            f"Transkriptbasis {item_number}: Gespräch mit mehreren Personen über {scenario['title']}.",
            f"Eine Person verteidigt {scenario['goal']}, eine andere nennt {scenario['issue']}.",
            f"Im Gespräch entstehen verschiedene Lösungsvorschläge, darunter {scenario['solution']}.",
        ]
    return [
        f"Transkriptbasis {item_number}: {part['title']}.",
        f"Hörsituation: {scenario['title']} · {scenario['setting']}.",
    ]


def _leitpunkte(module: str, part: dict[str, Any], scenario: dict[str, Any]) -> list[str]:
    title_lower = f"{part['key']} {part['title']} {part['instructions']}".lower()
    if module == "schreiben":
        if "formular" in title_lower:
            return [
                "Tragen Sie persönliche Angaben vollständig und passend ein.",
                "Achten Sie auf Namen, Datum, Adresse oder ähnliche Basisdaten.",
            ]
        if "kurzreferat" in title_lower or "überarbeiten" in title_lower:
            return [
                "Formulieren Sie die markierten Passagen neu.",
                "Behalten Sie die Aussage des Ausgangstextes bei.",
                "Nutzen Sie die vorgegebenen Wörter grammatisch korrekt.",
            ]
        if "forum" in title_lower or "diskussionsbeitrag" in title_lower:
            return [
                f"Führen Sie in das Thema {scenario['title']} ein.",
                f"Nehmen Sie klar Stellung zu {scenario['goal']}.",
                "Begründen Sie Ihre Meinung mit mindestens einem passenden Beispiel.",
                "Schließen Sie den Beitrag sinnvoll und adressatenorientiert ab.",
            ]
        if "leserbrief" in title_lower or "buchbesprechung" in title_lower or "ausführlicher text" in title_lower:
            return [
                "Wählen Sie ein Thema und legen Sie Ihre Position deutlich fest.",
                "Entwickeln Sie Ihre Argumentation differenziert weiter.",
                "Arbeiten Sie Beispiele, Folgen oder Gegenargumente ein.",
                "Achten Sie auf ein durchgehend passendes Register.",
            ]
        return [
            f"Nennen Sie den Anlass: {scenario['issue']}.",
            f"Formulieren Sie Ihr Ziel: {scenario['goal']}.",
            "Bearbeiten Sie alle Leitpunkte vollständig und logisch geordnet.",
            "Beenden Sie den Text passend zur Situation.",
        ]
    if "vorstellen" in title_lower:
        return [
            "Nennen Sie grundlegende persönliche Informationen.",
            "Sprechen Sie langsam, klar und vollständig.",
        ]
    if "fragen" in title_lower:
        return [
            "Stellen Sie eine passende Frage zum Thema.",
            "Antworten Sie direkt und fügen Sie ein Detail hinzu.",
        ]
    if "bitten" in title_lower:
        return [
            "Formulieren Sie eine Bitte eindeutig.",
            "Reagieren Sie passend auf die Bitte der anderen Person.",
        ]
    if "planen" in title_lower:
        return [
            "Machen Sie mindestens einen konkreten Vorschlag.",
            "Reagieren Sie auf den Vorschlag der anderen Person.",
            "Kommen Sie zu einer gemeinsamen Entscheidung.",
        ]
    if "vortrag" in title_lower or "präsentation" in title_lower or "produktion" in title_lower:
        return [
            f"Führen Sie in das Thema {scenario['title']} ein.",
            f"Entwickeln Sie zwei nachvollziehbare Punkte zu {scenario['goal']}.",
            "Nennen Sie ein Beispiel oder eine Erfahrung.",
            "Schließen Sie mit einem klaren Fazit und reagieren Sie auf Nachfragen.",
        ]
    return [
        "Nennen Sie Ihre Position klar und begründet.",
        "Greifen Sie das Argument oder die Frage der anderen Person auf.",
        "Reagieren Sie flexibel und schließen Sie die Aufgabe sinnvoll ab.",
    ]


def _objective_prompt(part: dict[str, Any], item_number: int) -> str:
    prefix = f"{part['title']} · Aufgabe {item_number}:"
    item_kind = str(part.get("item_kind", "mcq3"))
    if item_kind == "matching_speakers":
        return f"{prefix} Welche Zuordnung zu den Sprechenden passt?"
    if item_kind == "matching_headings":
        return f"{prefix} Welche Überschrift passt am besten?"
    if item_kind == "matching_locations":
        return f"{prefix} Welche Information oder welcher Ort passt?"
    if item_kind in {"matching_letters", "matching_words"}:
        return f"{prefix} Welche Zuordnung ist richtig?"
    if item_kind in {"true_false", "yes_no"}:
        return f"{prefix} Ist die Aussage korrekt?"
    return f"{prefix} Welche Lösung ist richtig?"


def _support_text(level: str, module: str, part: dict[str, Any], scenario: dict[str, Any], item_number: int) -> str:
    base = _source_frame(level, module, part, scenario, item_number)
    base.append(f"Offizieller Teilrahmen: {part['instructions']}")
    choice_legend = _choice_legend(part, scenario)
    if choice_legend:
        base.append("Antwortmöglichkeiten:")
        base.extend(choice_legend)
    if part.get("audio_plays"):
        base.append(f"Offizieller Hörrahmen: {part['audio_plays']} Hördurchgang/Hördurchgänge.")
    return "\n".join(base)


def _open_support_text(module: str, part: dict[str, Any], scenario: dict[str, Any]) -> str:
    details = [
        f"Offizieller Teilrahmen: {part['instructions']}",
        f"Prüfungssituation: {scenario['title']} · {scenario['setting']}",
        "Leitpunkte:",
        *[f"- {point}" for point in _leitpunkte(module, part, scenario)],
    ]
    if part.get("min_words"):
        details.append(f"Offizieller Orientierungswert: mindestens {part['min_words']} Wörter.")
    elif part.get("expected_words"):
        details.append(f"Orientierungswert: circa {part['expected_words']} Wörter bzw. entsprechender freier Beitrag.")
    for note in part.get("notes", []):
        details.append(str(note))
    if module == "sprechen":
        details.append("Sprechen Sie frei, klar gegliedert und reagieren Sie auf die Gesprächssituation.")
    else:
        details.append("Bearbeiten Sie alle Leitpunkte vollständig und achten Sie auf ein passendes Register.")
    return "\n".join(details)


def _goethe_exam_items(level: str, module: str, scenarios: list[dict[str, Any]]) -> list[ExerciseItem]:
    module_def = _module_def(level, module)
    parts: list[dict[str, Any]] = list(module_def["parts"])
    total_slots = sum(int(part.get("item_count") or 1) for part in parts)
    point_plan = _distribute_points(int(module_def["scoring"]["max_points"]), total_slots)
    items: list[ExerciseItem] = []
    point_index = 0
    for part_index, part in enumerate(parts):
        scenario = scenarios[min(part_index, len(scenarios) - 1)] if scenarios else topic_payload(None)
        part_slots = int(part.get("item_count") or 1)
        if module in {"lesen", "hoeren"}:
            for item_number in range(part_slots):
                items.append(
                    _objective_item(
                        level=level,
                        module=module,
                        part=part,
                        scenario=scenario,
                        item_number=item_number,
                        points=point_plan[point_index],
                    )
                )
                point_index += 1
            continue
        part_points = sum(point_plan[point_index : point_index + part_slots])
        point_index += part_slots
        items.append(_open_item(level=level, module=module, part=part, scenario=scenario, points=part_points))
    return items


def generate_exam(req: ExamGenerateRequest) -> ExamPayload:
    ensure_local_user()
    official = _official(req.level, req.scope, req.module)
    modules = ["lesen", "hoeren", "schreiben", "sprechen"] if req.scope == "full" else [req.module]
    parts: list[ExamPart] = []
    criteria: list[str] = []
    for module in modules:
        module_def = _module_def(req.level, module)
        parts.extend(_official_module_parts(module_def))
        criteria.extend(module_def["scoring"]["criteria"])
    started_at = perf_counter()
    mock_generation = generate_goethe_mock_exam(req, official)
    elapsed_ms = round((perf_counter() - started_at) * 1000)
    duration = sum(module.duration_minutes + module.prep_minutes for module in official.modules)
    payload = ExamPayload(
        exercise_id=make_id("exam"),
        institution=req.institution,
        scope=req.scope,
        module="full" if req.scope == "full" else req.module,
        selected_module=req.module if req.scope == "module" else None,
        level=req.level,
        duration_minutes=duration,
        title=official.title if req.scope == "full" else f"{official.title} · {req.module.title()}",
        instructions="Arbeiten Sie Teil für Teil in offizieller Reihenfolge. Zeiten, Teilanzahl und Aufgabentypen entsprechen den veröffentlichten Goethe-Unterlagen.",
        official_style_note="Die Struktur bleibt exakt an den offiziellen Goethe-Materialien ausgerichtet. Die Aufgabeninhalte werden original für diese App erzeugt und gegen einen Goethe-Blueprint validiert.",
        source_framework=mock_generation.source_framework,
        cefr_focus=list(dict.fromkeys(criteria)),
        parts=parts,
        official_reference=official,
        items=mock_generation.items,
        criteria=list(dict.fromkeys(criteria)),
        variant_seed=mock_generation.variant_seed,
        generator_version=mock_generation.generator_version,
        generation_mode=mock_generation.generation_mode,
        calibration_notes=mock_generation.calibration_notes,
        validation_notes=mock_generation.validation_notes,
        fallback_used=mock_generation.fallback_used,
        generation_elapsed_ms=elapsed_ms,
        module_brief_used=mock_generation.module_brief_used,
        mock_audio_voice_gender=req.mock_audio_voice_gender,
        mock_media_pack=mock_generation.mock_media_pack,
    )
    telemetry_run = save_mock_generation_run(
        level=req.level,
        module=payload.module,
        scope=req.scope,
        variant_seed=mock_generation.variant_seed,
        generation_mode=mock_generation.generation_mode,
        fallback_used=mock_generation.fallback_used,
        llm_model=mock_generation.llm_model,
        elapsed_ms=elapsed_ms,
        item_count=len(mock_generation.items),
        media_pack_count=len(mock_generation.mock_media_pack),
        validation_notes=mock_generation.validation_notes,
        module_brief_used=mock_generation.module_brief_used,
    )
    save_exercise(
        exercise_id=payload.exercise_id,
        category="exam",
        module=payload.module,
        level=req.level,
        title=payload.title,
        prompt_payload=payload.model_dump(),
        answer_payload={"items": [item.model_dump() for item in mock_generation.items]},
        criteria_payload=payload.criteria,
        meta_payload={
            "institution": req.institution,
            "scope": req.scope,
            "selected_module": req.module,
            "recommendation_event_id": req.recommendation_event_id,
            "variant_seed": mock_generation.variant_seed,
            "generator_version": mock_generation.generator_version,
            "generation_mode": mock_generation.generation_mode,
            "fallback_used": mock_generation.fallback_used,
            "generation_elapsed_ms": elapsed_ms,
            "module_brief_used": mock_generation.module_brief_used,
            "mock_generation_run_id": telemetry_run.run_id,
            "mock_audio_voice_gender": req.mock_audio_voice_gender,
            "validation_notes": mock_generation.validation_notes,
        },
    )
    return payload


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _content_terms(text: str) -> set[str]:
    return {
        _as_ascii_key(word)
        for word in split_words(text)
        if len(word) >= 4 and _as_ascii_key(word) not in OPEN_RESPONSE_STOPWORDS
    }


def _extract_leitpunkte(item: ExerciseItem) -> list[str]:
    return [
        line[2:].strip()
        for line in str(item.support_text or "").splitlines()
        if line.strip().startswith("- ")
    ]


def _keyword_hits(text: str, keywords: list[str]) -> int:
    haystack = _as_ascii_key(text)
    return sum(1 for keyword in keywords if keyword and _as_ascii_key(keyword) in haystack)


def _marker_hits(text: str, markers: set[str]) -> int:
    haystack = _as_ascii_key(text)
    return sum(1 for marker in markers if marker and marker in haystack)


def _marker_ratio(text: str, markers: set[str], target_hits: int) -> float:
    return _clamp(_marker_hits(text, markers) / max(target_hits, 1))


def _leitpunkt_hits(text: str, leitpunkte: list[str]) -> int:
    answer_terms = _content_terms(text)
    if not answer_terms:
        return 0
    hits = 0
    for point in leitpunkte:
        point_terms = _content_terms(point)
        if point_terms and answer_terms & point_terms:
            hits += 1
    return hits


def _prompt_overlap_ratio(text: str, item: ExerciseItem) -> float:
    answer_terms = _content_terms(text)
    if not answer_terms:
        return 0.0
    reference_terms = _content_terms(" ".join([item.prompt, item.support_text or "", " ".join(item.keywords)]))
    if not reference_terms:
        return 0.0
    return len(answer_terms & reference_terms) / max(1, min(len(answer_terms), len(reference_terms)))


def _infer_open_task_profile(item: ExerciseItem) -> dict[str, bool]:
    haystack = _as_ascii_key(" ".join([item.section or "", item.section_title or "", item.prompt, item.support_text or ""]))
    extended_text = any(marker in haystack for marker in ["ausfuehrlicher text", "buchbesprechung", "essay", "rezension", "leserbrief"])
    return {
        "formal": (not extended_text) and any(marker in haystack for marker in ["nachricht", "beschwerde", "beruflich", "formell"]),
        "argumentative": any(marker in haystack for marker in ["forum", "diskussionsbeitrag", "diskussion", "vortrag", "praesentation", "produktion"]),
        "interactive": bool(item.section == "sprechen" and any(marker in haystack for marker in ["diskussion", "interaktion", "planen", "fragen", "nachfragen"])),
        "presentation": bool(item.section == "sprechen" and any(marker in haystack for marker in ["vortrag", "praesentation", "produktion"])),
        "discussion": bool(item.section == "sprechen" and any(marker in haystack for marker in ["diskussion", "interaktion", "planen"])),
        "message": (not extended_text) and any(marker in haystack for marker in ["nachricht", "e-mail", "beschwerde"]),
        "forum": any(marker in haystack for marker in ["forum", "diskussionsbeitrag"]),
        "rewrite": any(marker in haystack for marker in ["umformung", "ueberarbeiten", "kurzreferat"]),
        "extended_text": extended_text,
        "review": "buchbesprechung" in haystack,
        "high_level_speaking": bool(item.section == "sprechen" and any(marker in haystack for marker in ["fachdebatte", "fachanhoerung", "kulturpolitisch", "theoretisch", "differenziert"])),
    }


def _is_nonanswer_response(text: str) -> bool:
    normalized = _as_ascii_key(" ".join(text.split()))
    if not normalized:
        return True
    return any(marker in normalized for marker in OPEN_NONANSWER_MARKERS)


def _strict_exam_objective_result(user_answer: str, expected_answer: str) -> tuple[float, str]:
    normalized_user = _as_ascii_key(user_answer)
    normalized_expected = _as_ascii_key(expected_answer)
    if not normalized_user:
        return 0.0, "Keine Antwort abgegeben."
    if normalized_user == normalized_expected:
        return 1.0, "Richtig."
    return 0.0, "Die Antwort stimmt nicht mit dem offiziellen Loesungsschluessel dieser Aufgabe ueberein."


def _open_task_policy(level: str, item: ExerciseItem, profile: dict[str, bool]) -> dict[str, float]:
    base = dict(OPEN_LEVEL_POLICY.get(level, OPEN_LEVEL_POLICY["B2"]))
    policy = {
        "task_floor": base["task_floor"],
        "length_floor": base["length_floor"],
        "structure_floor": base["structure_floor"],
        "register_floor": base["register_floor"],
        "language_floor": base["language_floor"],
        "precision_floor": base["precision_floor"],
        "task_fail_cap": 0.56,
        "length_fail_cap": 0.58,
        "structure_fail_cap": 0.6,
        "register_fail_cap": 0.62,
        "language_fail_cap": 0.66,
        "precision_fail_cap": 0.72,
        "interaction_floor": 0.0,
        "interaction_fail_cap": 0.58,
        "discourse_floor": 0.0,
        "discourse_fail_cap": 0.78,
        "signpost_floor": 0.0,
        "signpost_fail_cap": 0.76,
        "excellence_threshold": 0.94 if level in {"A1", "A2", "B1", "B2"} else 0.96,
    }
    if item.section == "sprechen":
        policy["length_floor"] = max(0.48, policy["length_floor"] - 0.12)
        policy["structure_floor"] = min(0.82, policy["structure_floor"] + 0.08)
        policy["language_fail_cap"] = min(policy["language_fail_cap"], 0.6 if level in {"C1", "C2"} else 0.64)
        if profile["discussion"]:
            policy["register_floor"] = min(0.9, policy["register_floor"] + 0.08)
            policy["interaction_floor"] = 0.76 if level in {"B2", "C1", "C2"} else 0.62
            policy["interaction_fail_cap"] = 0.42 if level in {"C1", "C2"} else 0.48
            policy["task_fail_cap"] = min(policy["task_fail_cap"], 0.52)
            policy["discourse_floor"] = 0.52 if level in {"C1", "C2"} else 0.34
            policy["discourse_fail_cap"] = 0.62 if level in {"C1", "C2"} else 0.7
        elif profile["presentation"]:
            policy["structure_floor"] = min(0.9, policy["structure_floor"] + 0.08)
            policy["register_floor"] = max(0.48, policy["register_floor"] - 0.04)
            policy["interaction_floor"] = 0.42 if level in {"C1", "C2"} else 0.34
            policy["interaction_fail_cap"] = 0.62
            policy["signpost_floor"] = 0.56 if level in {"C1", "C2"} else 0.42
            policy["signpost_fail_cap"] = 0.64 if level in {"C1", "C2"} else 0.72
            policy["discourse_floor"] = 0.48 if level in {"C1", "C2"} else 0.34
            policy["discourse_fail_cap"] = 0.68 if level in {"C1", "C2"} else 0.74
    if (profile["formal"] or profile["message"]) and not profile["extended_text"]:
        policy["register_floor"] = min(0.92, policy["register_floor"] + 0.12)
        policy["register_fail_cap"] = min(policy["register_fail_cap"], 0.48 if level in {"C1", "C2"} else 0.54)
    if profile["forum"]:
        policy["task_floor"] = min(0.9, policy["task_floor"] + 0.04)
        policy["structure_floor"] = min(0.9, policy["structure_floor"] + 0.04)
        policy["discourse_floor"] = max(policy["discourse_floor"], 0.44 if level in {"C1", "C2"} else 0.32)
    if profile["rewrite"]:
        policy["task_floor"] = min(0.94, policy["task_floor"] + 0.1)
        policy["length_floor"] = max(0.45, policy["length_floor"] - 0.16)
        policy["structure_floor"] = max(0.32, policy["structure_floor"] - 0.12)
        policy["language_floor"] = min(0.92, policy["language_floor"] + 0.1)
        policy["precision_floor"] = min(0.92, policy["precision_floor"] + 0.08)
        policy["task_fail_cap"] = min(policy["task_fail_cap"], 0.46)
        policy["language_fail_cap"] = min(policy["language_fail_cap"], 0.54)
        policy["precision_fail_cap"] = min(policy["precision_fail_cap"], 0.58)
    if profile["extended_text"]:
        policy["task_floor"] = min(0.96, policy["task_floor"] + 0.04)
        policy["length_floor"] = min(0.98, policy["length_floor"] + (0.04 if level == "C2" else 0.02))
        policy["structure_floor"] = min(0.96, policy["structure_floor"] + (0.08 if level == "C2" else 0.04))
        policy["precision_floor"] = min(0.96, policy["precision_floor"] + (0.08 if level == "C2" else 0.04))
        policy["language_floor"] = min(0.96, policy["language_floor"] + (0.06 if level == "C2" else 0.03))
        policy["discourse_floor"] = max(policy["discourse_floor"], 0.62 if level == "C2" else 0.48)
        policy["discourse_fail_cap"] = min(policy["discourse_fail_cap"], 0.54 if level == "C2" else 0.64)
    if profile["review"] and level == "C2":
        policy["register_floor"] = min(0.96, policy["register_floor"] + 0.06)
        policy["precision_floor"] = min(0.96, policy["precision_floor"] + 0.04)
    if level in {"C1", "C2"}:
        policy["task_fail_cap"] = min(policy["task_fail_cap"], 0.52)
        policy["length_fail_cap"] = min(policy["length_fail_cap"], 0.54)
        policy["structure_fail_cap"] = min(policy["structure_fail_cap"], 0.56)
        policy["register_fail_cap"] = min(policy["register_fail_cap"], 0.56)
        policy["excellence_threshold"] = 0.97 if level == "C2" else 0.96
        if item.section == "sprechen":
            policy["signpost_floor"] = max(policy["signpost_floor"], 0.52 if profile["presentation"] else 0.0)
            policy["discourse_floor"] = max(policy["discourse_floor"], 0.44 if profile["discussion"] else policy["discourse_floor"])
    return policy


def _goethe_aligned_open_feedback(
    level: str,
    user_answer: str,
    item: ExerciseItem,
    module_payload: OfficialExamModule | None,
) -> tuple[float, str, str | None, list[Any]]:
    min_words = item.min_words or 40
    profile = _infer_open_task_profile(item)
    policy = _open_task_policy(level, item, profile)
    corrected_version, detected_issues = detect_generic_errors(
        user_answer,
        min_words=min_words,
        require_question=profile["discussion"],
    )
    words = split_words(user_answer)
    word_count = len(words)
    sentence_count = len(
        [segment for segment in re.split(r"[.!?]+", user_answer.replace("\n", " ")) if split_words(segment)]
    )
    lexical_variety = (len({_as_ascii_key(word) for word in words}) / max(word_count, 1)) if words else 0.0
    keyword_hits = _keyword_hits(user_answer, item.keywords)
    leitpunkte = _extract_leitpunkte(item)
    leitpunkt_hits = _leitpunkt_hits(user_answer, leitpunkte)
    overlap_ratio = _prompt_overlap_ratio(user_answer, item)
    keyword_ratio = keyword_hits / max(1, len(item.keywords))
    leitpunkt_ratio = leitpunkt_hits / max(1, len(leitpunkte)) if leitpunkte else keyword_ratio
    task_ratio = max(keyword_ratio, (leitpunkt_ratio * 0.7) + (overlap_ratio * 0.3))

    criteria = list(module_payload.scoring.criteria if module_payload else EXAM_CRITERIA.get(item.section or "", []))
    feedback_bits: list[str] = []

    if _is_nonanswer_response(user_answer):
        detected_issues.append(build_error_insight("aufgabenbezug", item.prompt, "Es wurde keine verwertbare Antwort abgegeben."))
        feedback_bits.append("Keine verwertbare Antwort: fuer diese produktive Aufgabe werden ohne Inhalt keine Punkte vergeben.")
        if criteria:
            feedback_bits.insert(0, f"Goethe-aligned Evaluation nach Kriterien wie {', '.join(criteria[:4])}.")
        return 0.0, " ".join(feedback_bits), None, dedupe_errors(detected_issues)

    if word_count < max(8, int(min_words * 0.12)) and task_ratio < 0.18:
        detected_issues.append(build_error_insight("aufgabenbezug", item.prompt, f"Die Antwort bleibt mit {word_count} Woertern deutlich unter dem pruefungsnahen Minimum."))
        feedback_bits.append(f"Die Antwort ist fuer die Aufgabe deutlich zu kurz ({word_count} Woerter) und deckt die Leitpunkte nicht erkennbar ab.")
        if criteria:
            feedback_bits.insert(0, f"Goethe-aligned Evaluation nach Kriterien wie {', '.join(criteria[:4])}.")
        return 0.0, " ".join(feedback_bits), None, dedupe_errors(detected_issues)

    length_ratio = _clamp(word_count / max(min_words, 1))
    structure_ratio = 0.0
    if sentence_count >= 4:
        structure_ratio = 1.0
    elif sentence_count == 3:
        structure_ratio = 0.78
    elif sentence_count == 2:
        structure_ratio = 0.52
    elif sentence_count == 1:
        structure_ratio = 0.18

    register_ratio = 0.58
    normalized_answer = _as_ascii_key(user_answer)
    if profile["formal"]:
        register_ratio = 1.0 if any(marker in normalized_answer for marker in OPEN_FORMAL_MARKERS) else 0.35
    elif profile["interactive"]:
        register_ratio = 1.0 if any(marker in normalized_answer for marker in OPEN_INTERACTION_MARKERS) else 0.4
    elif profile["argumentative"]:
        register_ratio = 1.0 if any(marker in normalized_answer for marker in OPEN_ARGUMENT_MARKERS) else 0.5
    elif profile["extended_text"]:
        register_ratio = 0.9 if (_marker_hits(user_answer, OPEN_ARGUMENT_MARKERS) + _marker_hits(user_answer, OPEN_DISCOURSE_MARKERS)) >= 4 else 0.58
    elif profile["rewrite"]:
        register_ratio = 0.85 if sentence_count >= 2 else 0.45

    language_ratio = _clamp(1.0 - (len(detected_issues) * 0.14), 0.0, 1.0)
    vocab_ratio = _clamp((lexical_variety - 0.32) / 0.36)
    precision_ratio = _clamp((lexical_variety - 0.26) / 0.42)
    discourse_ratio = _marker_ratio(user_answer, OPEN_DISCOURSE_MARKERS, 4 if profile["extended_text"] else 2)
    signpost_ratio = _marker_ratio(user_answer, OPEN_PRESENTATION_MARKERS, 3 if profile["presentation"] else 2)
    counterargument_ratio = _marker_ratio(user_answer, OPEN_COUNTERARGUMENT_MARKERS, 2 if profile["discussion"] else 1)
    interaction_ratio = 1.0
    if profile["discussion"]:
        interaction_ratio = _clamp((_marker_ratio(user_answer, OPEN_INTERACTION_MARKERS, 2) * 0.65) + (counterargument_ratio * 0.35), 0.0, 1.0)
        if interaction_ratio <= 0.05:
            interaction_ratio = 0.28
    elif profile["presentation"] and profile["interactive"]:
        interaction_ratio = _clamp((_marker_ratio(user_answer, OPEN_INTERACTION_MARKERS, 1) * 0.55) + (signpost_ratio * 0.45), 0.0, 1.0)
        if interaction_ratio <= 0.05:
            interaction_ratio = 0.48
    if profile["rewrite"]:
        raw_ratio = (
            (task_ratio * 0.48)
            + (length_ratio * 0.08)
            + (structure_ratio * 0.08)
            + (register_ratio * 0.04)
            + (language_ratio * 0.2)
            + (precision_ratio * 0.12)
        )
    elif profile["extended_text"]:
        raw_ratio = (
            (task_ratio * 0.34)
            + (length_ratio * 0.16)
            + (structure_ratio * 0.12)
            + (register_ratio * 0.08)
            + (language_ratio * 0.08)
            + (vocab_ratio * 0.06)
            + (precision_ratio * 0.08)
            + (discourse_ratio * 0.08)
        )
    elif item.section == "sprechen":
        raw_ratio = (
            (task_ratio * 0.3)
            + (length_ratio * 0.12)
            + (structure_ratio * 0.16)
            + (register_ratio * 0.1)
            + (language_ratio * 0.1)
            + (vocab_ratio * 0.04)
            + (interaction_ratio * 0.08)
            + (discourse_ratio * 0.05)
            + (signpost_ratio * 0.05)
        )
    else:
        raw_ratio = (
            (task_ratio * 0.42)
            + (length_ratio * 0.22)
            + (structure_ratio * 0.14)
            + (register_ratio * 0.1)
            + (language_ratio * 0.07)
            + (vocab_ratio * 0.05)
        )

    coverage_cap = 1.0
    if leitpunkte:
        if leitpunkt_ratio < 0.26:
            coverage_cap = min(coverage_cap, 0.16)
        elif leitpunkt_ratio < 0.5:
            coverage_cap = min(coverage_cap, 0.42)
        elif leitpunkt_ratio < 0.75:
            coverage_cap = min(coverage_cap, 0.72)
    if keyword_ratio < 0.2 and overlap_ratio < 0.18:
        coverage_cap = min(coverage_cap, 0.12)
    elif keyword_ratio < 0.4 and overlap_ratio < 0.28:
        coverage_cap = min(coverage_cap, 0.34)
    elif task_ratio < 0.55:
        coverage_cap = min(coverage_cap, 0.74)

    if task_ratio < 0.18:
        raw_ratio = min(raw_ratio, 0.04)
    elif task_ratio < 0.3:
        raw_ratio = min(raw_ratio, 0.14)

    length_cap = 1.0
    if word_count < max(12, int(min_words * 0.25)):
        length_cap = 0.08
    elif word_count < max(18, int(min_words * 0.45)):
        length_cap = 0.22
    elif word_count < max(26, int(min_words * 0.65)):
        length_cap = 0.45
    elif word_count < int(min_words * 0.85):
        length_cap = 0.72
    elif word_count < min_words:
        length_cap = 0.9

    structure_cap = 1.0
    if sentence_count <= 1:
        structure_cap = 0.15
    elif sentence_count == 2:
        structure_cap = 0.42
    elif sentence_count == 3:
        structure_cap = 0.68

    register_cap = 1.0
    if register_ratio < 0.45:
        register_cap = 0.4
    elif register_ratio < 0.8:
        register_cap = 0.76

    interaction_cap = 1.0
    if profile["interactive"] and register_ratio < 0.8:
        interaction_cap = 0.45

    language_cap = 1.0
    if len(detected_issues) >= 5:
        language_cap = 0.4
    elif len(detected_issues) >= 3:
        language_cap = 0.62
    elif len(detected_issues) >= 2:
        language_cap = 0.8

    discourse_cap = 1.0
    if profile["extended_text"] and discourse_ratio < 0.28:
        discourse_cap = 0.34 if level == "C2" else 0.46
    elif (profile["extended_text"] or profile["discussion"] or profile["presentation"]) and discourse_ratio < 0.48:
        discourse_cap = 0.66
    elif (profile["extended_text"] or profile["discussion"] or profile["presentation"]) and discourse_ratio < 0.68:
        discourse_cap = 0.82

    signpost_cap = 1.0
    if profile["presentation"] and signpost_ratio < 0.24:
        signpost_cap = 0.48 if level in {"C1", "C2"} else 0.62
    elif profile["presentation"] and signpost_ratio < 0.5:
        signpost_cap = 0.74

    task_floor_cap = 1.0 if task_ratio >= policy["task_floor"] else policy["task_fail_cap"]
    length_floor_cap = 1.0 if length_ratio >= policy["length_floor"] else policy["length_fail_cap"]
    structure_floor_cap = 1.0 if structure_ratio >= policy["structure_floor"] else policy["structure_fail_cap"]
    register_floor_cap = 1.0 if register_ratio >= policy["register_floor"] else policy["register_fail_cap"]
    language_floor_cap = 1.0 if language_ratio >= policy["language_floor"] else policy["language_fail_cap"]
    precision_floor_cap = 1.0 if precision_ratio >= policy["precision_floor"] else policy["precision_fail_cap"]
    interaction_floor_cap = 1.0
    if policy["interaction_floor"] > 0 and interaction_ratio < policy["interaction_floor"]:
        interaction_floor_cap = policy["interaction_fail_cap"]
    discourse_floor_cap = 1.0
    if policy["discourse_floor"] > 0 and discourse_ratio < policy["discourse_floor"]:
        discourse_floor_cap = policy["discourse_fail_cap"]
    signpost_floor_cap = 1.0
    if policy["signpost_floor"] > 0 and signpost_ratio < policy["signpost_floor"]:
        signpost_floor_cap = policy["signpost_fail_cap"]

    excellence_cap = policy["excellence_threshold"]
    if profile["extended_text"] and level in {"C1", "C2"}:
        if detected_issues:
            excellence_cap = min(excellence_cap, 0.9)
        if leitpunkte and leitpunkt_ratio < 1.0:
            excellence_cap = min(excellence_cap, 0.88 if level == "C2" else 0.9)
        if word_count < int(min_words * 1.1):
            excellence_cap = min(excellence_cap, 0.9)
        if discourse_ratio < 0.82 or precision_ratio < max(0.48, policy["precision_floor"] + 0.04):
            excellence_cap = min(excellence_cap, 0.9)
    if item.section == "sprechen" and level in {"C1", "C2"}:
        if detected_issues:
            excellence_cap = min(excellence_cap, 0.9)
        if word_count < max(int(min_words * 1.35), min_words + 20):
            excellence_cap = min(excellence_cap, 0.9)
        if task_ratio < 0.88:
            excellence_cap = min(excellence_cap, 0.88)
        if profile["discussion"] and ("?" not in user_answer or counterargument_ratio < 0.75):
            excellence_cap = min(excellence_cap, 0.88)
        if profile["discussion"] and interaction_ratio < 0.92:
            excellence_cap = min(excellence_cap, 0.9)
        if profile["presentation"] and signpost_ratio < 0.82:
            excellence_cap = min(excellence_cap, 0.9)
    if excellence_cap >= policy["excellence_threshold"] and (
        task_ratio >= max(0.84, policy["task_floor"] + 0.18)
        and length_ratio >= 1.0
        and structure_ratio >= max(0.78, policy["structure_floor"] + 0.14)
        and register_ratio >= max(0.8, policy["register_floor"] + 0.12)
        and language_ratio >= max(0.86, policy["language_floor"] + 0.14)
        and vocab_ratio >= 0.35
        and precision_ratio >= max(0.34, policy["precision_floor"])
        and interaction_ratio >= max(0.72, policy["interaction_floor"] or 0.0)
        and discourse_ratio >= max(0.72, policy["discourse_floor"] or 0.0)
        and signpost_ratio >= max(0.56, policy["signpost_floor"] or 0.0)
        and (not profile["extended_text"] or not leitpunkte or leitpunkt_ratio >= 1.0)
        and len(detected_issues) <= 1
    ):
        excellence_cap = 1.0

    raw_ratio = min(
        raw_ratio,
        coverage_cap,
        length_cap,
        structure_cap,
        register_cap,
        interaction_cap,
        language_cap,
        discourse_cap,
        signpost_cap,
        task_floor_cap,
        length_floor_cap,
        structure_floor_cap,
        register_floor_cap,
        language_floor_cap,
        precision_floor_cap,
        interaction_floor_cap,
        discourse_floor_cap,
        signpost_floor_cap,
        excellence_cap,
    )

    item_score = round(item.points * _clamp(raw_ratio), 2)

    if word_count < min_words:
        detected_issues.append(
            build_error_insight(
                "aufgabenbezug",
                item.prompt,
                f"Der Beitrag bleibt fuer die Zielaufgabe zu kurz ({word_count}/{min_words} Woerter).",
            )
        )
    if task_ratio < 0.4:
        detected_issues.append(
            build_error_insight(
                "aufgabenbezug",
                item.prompt,
                f"Leitpunkte und Aufgabenfokus sind noch zu duenn abgedeckt ({leitpunkt_hits}/{max(len(leitpunkte), 1)} Leitpunkte, {keyword_hits}/{max(len(item.keywords), 1)} Leitwoerter).",
            )
        )
    if structure_ratio < 0.45:
        detected_issues.append(build_error_insight("koharenz", item.prompt))
    if register_ratio < 0.45:
        detected_issues.append(build_error_insight("register", item.prompt))
    if vocab_ratio < 0.25:
        detected_issues.append(build_error_insight("wortschatz", item.prompt))
    if policy["interaction_floor"] > 0 and interaction_ratio < policy["interaction_floor"]:
        detected_issues.append(build_error_insight("interaktion", item.prompt, "Die Aufgabe verlangt mehr sichtbare Reaktion auf Gegenargumente, Rueckfragen oder Gespraechsimpulse."))
    if policy["discourse_floor"] > 0 and discourse_ratio < policy["discourse_floor"]:
        detected_issues.append(build_error_insight("koharenz", item.prompt, "Der Beitrag braucht deutlich mehr klare Strukturmarker und nachvollziehbare Gedankengelenke."))
    if policy["signpost_floor"] > 0 and signpost_ratio < policy["signpost_floor"]:
        detected_issues.append(build_error_insight("koharenz", item.prompt, "Im Vortrag fehlen pruefungsnahe Signale fuer Einstieg, Gliederung und Abschluss."))

    coverage_note = (
        f"Aufgabenbezug solide ({leitpunkt_hits}/{max(len(leitpunkte), 1)} Leitpunkte, {keyword_hits}/{max(len(item.keywords), 1)} Leitwoerter)."
        if task_ratio >= 0.62
        else f"Aufgabenbezug noch zu duenn ({leitpunkt_hits}/{max(len(leitpunkte), 1)} Leitpunkte, {keyword_hits}/{max(len(item.keywords), 1)} Leitwoerter)."
    )
    structure_note = (
        f"Aufbau tragfaehig mit {sentence_count} Saetzen."
        if structure_ratio >= 0.78
        else f"Aufbau noch zu knapp; aktuell {sentence_count} Satz/Saetze."
    )
    register_note = (
        "Register und Kommunikationssituation wirken passend."
        if register_ratio >= 0.8
        else "Register bzw. Kommunikationshaltung wirken noch nicht ausreichend pruefungsnah."
    )
    quality_note = (
        "Sprachrichtigkeit und Wortschatz wirken insgesamt stabil."
        if language_ratio >= 0.72 and vocab_ratio >= 0.4
        else "Sprachrichtigkeit, Wortschatz oder Praezision bleiben noch hinter dem Goethe-Rahmen zurueck."
    )
    discourse_note = (
        "Die Gedankenfuehrung ist gut gegliedert und argumentativ nachvollziehbar."
        if discourse_ratio >= 0.68
        else "Die Gedankenfuehrung braucht noch klarere Verknuepfungen und staerkere textinterne Orientierung."
    )
    interaction_note = ""
    if profile["discussion"]:
        interaction_note = (
            "Die Diskussion greift Gegenargumente sichtbar auf und reagiert pruefungsnah auf Gespraechsimpulse."
            if interaction_ratio >= 0.72
            else "Die Diskussion reagiert noch zu wenig auf Gegenargumente oder direkte Gespraechsimpulse."
        )
    elif profile["presentation"]:
        interaction_note = (
            "Der Vortrag ist klar gegliedert und signalisiert Einstieg, Entwicklung und Abschluss deutlich."
            if signpost_ratio >= 0.58
            else "Der Vortrag braucht staerkere Signale fuer Einstieg, Gliederung und Abschluss."
        )
    level_note = ""
    if raw_ratio < 0.6:
        level_note = f"Fuer {level} {item.section.title()} reicht die Leistung im pruefungsnahen Goethe-Rahmen noch nicht an die Bestehensschwelle heran."
    elif raw_ratio < 0.78:
        level_note = f"Fuer {level} {item.section.title()} ist die Leistung solide, aber in Aufgabenbezug, Register oder sprachlicher Praezision noch nicht stabil genug."
    if criteria:
        feedback_bits.append(f"Goethe-aligned Evaluation nach Kriterien wie {', '.join(criteria[:4])}.")
    feedback_bits.extend([coverage_note, structure_note, register_note, quality_note, discourse_note])
    if interaction_note:
        feedback_bits.append(interaction_note)
    if level_note:
        feedback_bits.append(level_note)
    if word_count < min_words:
        feedback_bits.append(f"Der offizielle Orientierungswert wird klar verfehlt ({word_count}/{min_words} Woerter).")
    elif word_count < int(min_words * 0.85):
        feedback_bits.append(f"Der Text bleibt noch unter dem Orientierungswert ({word_count}/{min_words} Woerter).")

    deduped_issues = dedupe_errors(detected_issues)
    corrected_output = corrected_version if corrected_version and corrected_version != user_answer else None
    return item_score, " ".join(feedback_bits), corrected_output, deduped_issues


def _open_result_status(answered: bool, score: float, max_score: float) -> str:
    if not answered:
        return "empty"
    ratio = score / max(max_score, 1)
    if ratio <= 0.01:
        return "weak"
    if ratio < 0.22:
        return "weak"
    if ratio < 0.58:
        return "partial"
    if ratio < 0.92:
        return "strong"
    return "excellent"


def _objective_result_status(answered: bool, ratio: float) -> str:
    if not answered:
        return "empty"
    return "correct" if ratio >= 1.0 else "incorrect"


def submit_exam(req: ExamSubmitRequest) -> EvaluationPayload:
    exercise = get_exercise(req.exercise_id)
    if not exercise:
        raise ValueError("Prüfung nicht gefunden.")
    items = [ExerciseItem.model_validate(item) for item in exercise["prompt_json"]["items"]]
    official_reference = OfficialExamPayload.model_validate(exercise["prompt_json"]["official_reference"])
    official_modules = {module.key: module for module in official_reference.modules}
    results: list[ExerciseResultItem] = []
    errors: list[Any] = []
    score = 0.0
    max_score = 0.0
    sections: dict[str, dict[str, Any]] = {}
    answered_items = 0
    for item in items:
        user_answer = req.answers.get(item.id, "").strip()
        answered = bool(user_answer)
        if user_answer:
            answered_items += 1
        max_score += item.points
        corrected_version = None
        detected_issues: list[Any] = []
        status = "empty"
        if item.item_type in {"mcq", "short", "true_false", "fill_blank", "reorder"}:
            ratio, feedback = _strict_exam_objective_result(user_answer, item.answer)
            item_score = ratio * item.points
            corrected_version = item.answer if ratio < 1 else None
            status = _objective_result_status(answered, ratio)
        else:
            item_score, feedback, corrected_version, detected_issues = _goethe_aligned_open_feedback(
                exercise["level"],
                user_answer,
                item,
                official_modules.get(item.section) if item.section in official_modules else None,
            )
            status = _open_result_status(answered, item_score, item.points)
        if not user_answer and item_score > 0:
            item_score = 0.0
            feedback = "Keine Antwort abgegeben: 0 Punkte."
            corrected_version = item.answer if item.item_type in {"mcq", "short", "true_false", "fill_blank", "reorder"} else None
            detected_issues = [build_error_insight("aufgabenbezug", item.prompt, "Die Aufgabe wurde leer abgegeben.")]
            status = "empty"
        score += item_score
        section_key = item.section or "general"
        bucket = sections.setdefault(
            section_key,
            {
                "label": official_modules.get(section_key).label if section_key in official_modules else (item.section_title or section_key or "allgemein"),
                "score": 0.0,
                "max_score": 0.0,
            },
        )
        bucket["score"] += item_score
        bucket["max_score"] += item.points
        if item.item_type == "open":
            item_errors = detected_issues if item_score < item.points else []
            if item_score < item.points and not item_errors:
                item_errors = [build_error_insight("aufgabenbezug", item.prompt)]
        else:
            item_errors = [] if item_score >= item.points else [build_error_insight("aufgabenbezug" if item.section in {"schreiben", "sprechen"} else "grammatik", item.prompt)]
        errors.extend(item_errors)
        results.append(
            ExerciseResultItem(
                item_id=item.id,
                prompt=item.prompt,
                user_answer=user_answer,
                expected_answer=item.answer,
                score=round(item_score, 2),
                max_score=item.points,
                feedback=feedback,
                corrected_version=corrected_version,
                status=status,
                answered=answered,
                error_tags=item_errors,
            )
        )
    percent = round(score / max_score * 100, 1) if max_score else 0.0
    blank_submission = answered_items == 0
    if blank_submission:
        errors.insert(0, build_error_insight("aufgabenbezug", official_reference.title, "Die Pruefung wurde ohne verwertbare Antworten abgegeben."))
    attempt_id = save_attempt(
        exercise_id=req.exercise_id,
        category="exam",
        module=exercise["module"],
        level=exercise["level"],
        user_answers=req.answers,
        score=score,
        max_score=max_score,
        percent=percent,
        feedback_payload={"results": [result.model_dump() for result in results]},
        corrected_payload={"results": [result.corrected_version for result in results]},
        error_tags_payload=[error.model_dump() for error in errors],
        recommendation_event_id=_exercise_recommendation_event_id(exercise),
    )
    section_scores = [
        SectionScore(
            section_key=key,
            label=value["label"],
            score=round(value["score"], 2),
            max_score=float(official_modules.get(key).scoring.max_points if key in official_modules else value["max_score"]),
            pass_points=float(official_modules.get(key).scoring.pass_points if key in official_modules else 60.0),
            passed=value["score"] >= float(official_modules.get(key).scoring.pass_points if key in official_modules else 60.0),
            criteria=list(official_modules.get(key).scoring.criteria if key in official_modules else EXAM_CRITERIA.get(key, [])),
            note=(
                "Objektive Teile folgen dem Loesungsschluessel; produktive Teile werden Goethe-aligned "
                "auf Basis veroeffentlichter offizieller Kriterien bewertet."
            ),
        )
        for key, value in sections.items()
    ]
    failed_sections = [section.label for section in section_scores if not section.passed]
    passed = (not failed_sections) if section_scores else percent >= 60.0
    summary = (
        f"Leere Abgabe erkannt: 0 verwertbare Antworten. {official_reference.pass_rule}"
        if blank_submission
        else (
            f"Goethe-aligned Auswertung nach offizieller Struktur. Nicht bestanden in: {', '.join(failed_sections)}. {official_reference.pass_rule}"
            if failed_sections
            else f"Goethe-aligned Auswertung nach offizieller Struktur. Alle pruefungsrelevanten Sektionen liegen im Zielbereich. {official_reference.pass_rule}"
        )
    )
    return EvaluationPayload(
        attempt_id=attempt_id,
        exercise_id=req.exercise_id,
        title=exercise["title"],
        category="exam",
        module=exercise["module"],
        level=exercise["level"],
        score=round(score, 2),
        max_score=max_score,
        percent=percent,
        answered_count=answered_items,
        unanswered_count=max(0, len(items) - answered_items),
        passed=passed,
        failed_sections=failed_sections,
        summary=summary,
        recurring_errors=errors[:8],
        what_to_improve=(
            [
                "Bearbeiten Sie den naechsten Versuch nicht leer, sondern Teil fuer Teil in offizieller Reihenfolge.",
                "Beginnen Sie mit einem einzelnen Modul und halten Sie die offiziellen Wort- und Zeitvorgaben ein.",
                "Nutzen Sie die Leitpunkte sichtbar als Checkliste vor der Abgabe.",
            ]
            if blank_submission
            else [error.recommendation for error in errors[:5]]
        ),
        mini_drills=(
            [
                "Starten Sie mit einem einzelnen Goethe-Modul und beantworten Sie jede Aufgabe zumindest in einer Rohfassung.",
                "Ueben Sie zuerst nur die Leitpunkte der produktiven Teile, bevor Sie einen ganzen Mock abgeben.",
                "Nutzen Sie danach die Fehleransicht, um die naechste Variante gezielt zu verbessern.",
            ]
            if blank_submission
            else [
                "Wiederholen Sie zuerst nur die falsch beantworteten Aufgaben.",
            "Überarbeiten Sie mindestens eine produktive Antwort gezielt mit besserem Aufbau.",
            "Überführen Sie wiederkehrende Fehler direkt in Karteikarten.",
            ]
        ),
        study_plan=build_study_plan([error.tag for error in errors], f"goethe_{exercise['level'].lower()}"),
        section_scores=section_scores,
        results=results,
        official_alignment=(
            f"Modulstruktur, Zeiten und Aufgabentypen entsprechen den offiziellen Goethe-Unterlagen ({official_reference.official_version}). "
            "Die Bewertung ist Goethe-aligned und basiert bei produktiven Teilen auf veroeffentlichten offiziellen Kriterien, "
            "ohne als offizielle Goethe-Korrektur ausgegeben zu werden."
        ),
        pass_threshold=60.0,
    )


def generate_writing_prompt(req: WritingPromptRequest) -> WritingPromptPayload:
    ensure_local_user()
    scenario = topic_payload(req.topic)
    task = WRITING_TASKS[req.text_type]
    payload = WritingPromptPayload(
        prompt_id=make_id("writing"),
        level=req.level,
        target_exam=req.target_exam,
        text_type=req.text_type,
        title=task["title"],
        instructions=task["instruction"],
        bullet_points=[
            f"Erklären Sie das Problem: {scenario['issue']}.",
            f"Nennen Sie Ihr Ziel: {scenario['goal']}.",
            "Machen Sie einen konkreten Vorschlag oder bitten Sie um eine Lösung.",
        ],
        rubric=list(task["rubric"]),
        suggested_words=list(scenario["keywords"][:5]),
        official_alignment="Rubrik an veröffentlichte Goethe-Kriterien angelehnt.",
    )
    save_exercise(
        exercise_id=payload.prompt_id,
        category="writing",
        module=req.text_type,
        level=req.level,
        title=payload.title,
        prompt_payload=payload.model_dump(),
        answer_payload={"keywords": payload.suggested_words},
        criteria_payload=payload.rubric,
        meta_payload={
            "target_exam": req.target_exam,
            "recommendation_event_id": req.recommendation_event_id,
        },
    )
    return payload


def submit_writing(req: WritingGradeRequest) -> WritingGradePayload:
    exercise = get_exercise(req.prompt_id)
    if not exercise:
        raise ValueError("Schreibaufgabe nicht gefunden.")
    prompt = WritingPromptPayload.model_validate(exercise["prompt_json"])
    corrected_text, issues = detect_generic_errors(req.text, min_words=80 if prompt.level in {"B2", "C1"} else 50)
    rubric = [
        RubricScore(criterion="Aufgabenbezug", score=4.0 if len(req.text) > 120 else 3.0, max_score=5.0, comment="Leitpunkte und Aufgabenfokus."),
        RubricScore(criterion="Kommunikative Gestaltung", score=4.0 if "\n" in corrected_text or len(req.text.split(".")) > 2 else 3.0, max_score=5.0, comment="Aufbau, Leseführung und Klarheit."),
        RubricScore(criterion="Sprachrichtigkeit", score=max(1.0, 5.0 - len(issues) * 0.8), max_score=5.0, comment="Fehlerdichte und formale Sicherheit."),
        RubricScore(criterion="Wortschatz", score=min(5.0, 2.5 + len(set(req.text.lower().split())) / 35), max_score=5.0, comment="Lexikalische Reichweite und thematische Passung."),
    ]
    total = sum(item.score for item in rubric)
    max_total = sum(item.max_score for item in rubric)
    percent = round(total / max_total * 100, 1)
    attempt_id = save_attempt(
        exercise_id=req.prompt_id,
        category="writing",
        module=prompt.text_type,
        level=prompt.level,
        user_answers={"text": req.text},
        score=total,
        max_score=max_total,
        percent=percent,
        feedback_payload={"rubric": [item.model_dump() for item in rubric]},
        corrected_payload={"corrected_version": corrected_text},
        error_tags_payload=[item.model_dump() for item in issues],
        recommendation_event_id=_exercise_recommendation_event_id(exercise),
    )
    return WritingGradePayload(
        attempt_id=attempt_id,
        prompt_id=req.prompt_id,
        level=prompt.level,
        title=prompt.title,
        total_score=round(total, 2),
        max_score=max_total,
        percent=percent,
        corrected_version=corrected_text,
        rubric=rubric,
        recurring_errors=issues,
        what_to_improve=[item.recommendation for item in issues[:4]],
        tricks=[
            "Planen Sie zuerst Einleitung, Entwicklung und Schluss.",
            "Verwenden Sie mindestens einen Kausal- und einen Konnektor der Folge.",
            "Prüfen Sie am Ende Großschreibung und Kommas gezielt.",
        ],
        mini_drills=[
            "Überarbeiten Sie die Einleitung mit präziserem Fokus.",
            "Schreiben Sie drei neue Sätze mit `weil`, `deshalb` und `obwohl`.",
        ],
        study_plan=build_study_plan([item.tag for item in issues], f"goethe_{prompt.level.lower()}"),
        official_alignment="Rubrik an veröffentlichte Goethe-Kriterien angelehnt.",
    )


def generate_speaking_session(req: SpeakingSimulateRequest) -> SpeakingSimulationPayload:
    ensure_local_user()
    scenario = topic_payload(req.topic)
    flow = SPEAKING_SCENARIOS[req.mode]
    payload = SpeakingSimulationPayload(
        session_id=make_id("speaking"),
        level=req.level,
        target_exam=req.target_exam,
        mode=req.mode,
        title=flow["title"],
        scenario=f"{scenario['title']} · {scenario['setting']}",
        examiner_prompt=f"Sie möchten {scenario['goal']}. Erklären Sie zunächst, warum {scenario['issue']}.",
        evaluation_points=list(EXAM_CRITERIA["sprechen"]),
        suggested_phrases=[
            "Meiner Meinung nach ...",
            "Ich schlage vor, dass ...",
            "Könnten wir vielleicht ...?",
            "Ein wichtiger Punkt ist, dass ...",
        ],
        official_alignment="Sprechsimulation an veröffentlichten Goethe-Abläufen orientiert.",
    )
    now = utc_now_iso()
    with connection_scope() as conn:
        conn.execute(
            "INSERT INTO learning_sessions (id, session_type, level, title, target_exam, state_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                payload.session_id,
                "speaking",
                req.level,
                payload.title,
                req.target_exam,
                to_json(
                    {
                        "payload": payload.model_dump(),
                        "turn": 0,
                        "transcript": [{"speaker": "assistant", "text": payload.examiner_prompt}],
                        "recommendation_event_id": req.recommendation_event_id,
                    }
                ),
                now,
                now,
            ),
        )
    return payload


def submit_speaking_turn(req: SpeakingFeedbackRequest) -> SpeakingTurnPayload:
    with connection_scope() as conn:
        row = conn.execute("SELECT * FROM learning_sessions WHERE id = ?", (req.session_id,)).fetchone()
    if not row:
        raise ValueError("Sprechsitzung nicht gefunden.")
    state = json.loads(row["state_json"])
    payload = SpeakingSimulationPayload.model_validate(state["payload"])
    turn_number = int(state.get("turn", 0)) + 1
    corrected, issues = detect_generic_errors(req.user_message, min_words=12, require_question=turn_number == 3)
    replies = {
        1: "Danke. Können Sie das noch etwas genauer begründen?",
        2: "Gut. Reagieren Sie jetzt direkt und machen Sie einen konkreten Vorschlag.",
        3: "Vielen Dank. Das war die letzte Prüfungsrunde.",
    }
    reply_text = replies[turn_number]
    transcript_state = state.get("transcript")
    transcript = list(transcript_state) if isinstance(transcript_state, list) else []
    transcript.extend(
        [
            {"speaker": "user", "text": req.user_message},
            {"speaker": "assistant", "text": reply_text},
        ]
    )
    with connection_scope() as conn:
        conn.execute(
            "UPDATE learning_sessions SET state_json = ?, updated_at = ? WHERE id = ?",
            (
                to_json(
                    {
                        "payload": payload.model_dump(),
                        "turn": turn_number,
                        "transcript": transcript,
                        "recommendation_event_id": state.get("recommendation_event_id"),
                    }
                ),
                utc_now_iso(),
                req.session_id,
            ),
        )
    if turn_number >= 3:
        recommendation_event_id = str(state.get("recommendation_event_id") or "").strip() or None
        save_exercise(
            exercise_id=req.session_id,
            category="speaking",
            module=payload.mode,
            level=payload.level,
            title=payload.title,
            prompt_payload=payload.model_dump(),
            answer_payload={},
            criteria_payload=payload.evaluation_points,
            meta_payload={
                "target_exam": payload.target_exam,
                "recommendation_event_id": recommendation_event_id,
            },
        )
        save_attempt(
            exercise_id=req.session_id,
            category="speaking",
            module=payload.mode,
            level=payload.level,
            user_answers={
                "last_turn": req.user_message,
                "combined_response": "\n".join(
                    str(entry.get("text") or "").strip()
                    for entry in transcript
                    if str(entry.get("speaker") or "").strip().lower() == "user" and str(entry.get("text") or "").strip()
                ),
                "transcript": transcript,
            },
            score=max(6.0, 10.0 - len(issues)),
            max_score=10.0,
            percent=max(60.0, 100.0 - len(issues) * 10),
            feedback_payload={"feedback": [issue.description for issue in issues]},
            corrected_payload={"corrected": corrected},
            error_tags_payload=[issue.model_dump() for issue in issues],
            recommendation_event_id=recommendation_event_id,
        )
    return SpeakingTurnPayload(
        session_id=req.session_id,
        turn_number=turn_number,
        examiner_reply=reply_text,
        corrected_version=corrected,
        turn_feedback=[issue.description for issue in issues] or ["Die Antwort ist verständlich; jetzt noch präziser und besser entwickelt formulieren."],
        error_tags=issues,
        is_complete=turn_number >= 3,
        final_recommendation=build_study_plan([issue.tag for issue in issues], f"goethe_{payload.level.lower()}") if turn_number >= 3 else [],
    )


def generate_vocab(req: VocabFromTopicRequest) -> VocabPayload:
    ensure_local_user()
    lowered = req.topic.lower()
    topic_key = next((value for key, value in TOPIC_ALIASES.items() if key in lowered), "airport")
    bank = VOCAB_BANK.get(topic_key) or next(iter(VOCAB_BANK.values()))
    items = [
        VocabItem(
            id=make_id("vocab"),
            lemma=item["lemma"],
            pos=item["pos"],
            gender=item.get("gender"),
            plural=item.get("plural"),
            translation=item["translation"],
            level=item["level"],
            example=item["example"],
            collocation=item["collocation"],
            notes=item.get("notes", ""),
            topic=topic_key,
        )
        for item in stable_pick(bank, req.count, f"{topic_key}:{req.level}:{req.count}")
    ]
    return VocabPayload(topic=topic_key, level=req.level, items=items)
