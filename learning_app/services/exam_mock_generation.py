from __future__ import annotations

import json
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from ..goethe_blueprints import GOETHE_BLUEPRINT_VERSION, build_part_blueprint
from ..goethe_mock_bank import GOETHE_MOCK_SCENARIOS
from ..goethe_official import GOETHE_OFFICIAL_EXAMS
from ..schemas import ExamGenerateRequest, ExerciseItem, MockMediaSegment, OfficialExamPayload
from .common import stable_pick, topic_payload
from .exam_mock_llm import generate_structured_exam_part
from .exam_mock_validation import validate_objective_part_payload, validate_open_part_payload
from .mock_audio import ensure_mock_audio_segment

GENERATOR_VERSION = "goethe-mock-generator-v3"
MAX_GENERATION_ATTEMPTS = 2
MODULE_SCOPE_LLM_BUDGET_SEC = 12.0
FULL_SCOPE_LLM_BUDGET_SEC = 18.0
MIN_REMAINING_SEC_FOR_MODULE_BRIEF = 3.0
MIN_REMAINING_SEC_FOR_OPEN_LLM = 5.0

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

INTRO_FRAMES = {
    "A1": ["Im Mittelpunkt steht", "Es geht um", "Die Situation betrifft"],
    "A2": ["Das Thema ist", "Im Text geht es um", "Die Situation beschreibt"],
    "B1": ["Im Beitrag geht es um", "Im Zentrum steht", "Der Ausgangspunkt ist"],
    "B2": ["Der Text konzentriert sich auf", "Im Mittelpunkt des Beitrags steht", "Die Darstellung fokussiert"],
    "C1": ["Der Beitrag analysiert", "Die Darstellung reflektiert", "Der Text entfaltet"],
    "C2": ["Der Text entfaltet eine differenzierte Perspektive auf", "Die Vorlage lotet aus", "Der Beitrag verdichtet"],
}

FOLLOW_UP_FRAMES = {
    "A1": ["Dazu kommt", "Außerdem", "Dann"],
    "A2": ["Außerdem", "Danach", "Gleichzeitig"],
    "B1": ["Außerdem", "Gleichzeitig", "Daneben"],
    "B2": ["Zugleich", "Darüber hinaus", "Gleichzeitig"],
    "C1": ["Zugleich", "Darüber hinaus", "Im weiteren Verlauf"],
    "C2": ["Zugleich", "Im weiteren Verlauf", "Darüber hinaus"],
}

HEADING_BANK = [
    "Praktischer Nutzen im Alltag",
    "Unerwartete Folgen einer Entscheidung",
    "Zeitdruck und Organisation",
    "Konflikt zwischen Aufwand und Nutzen",
    "Gemeinsame Lösung statt Einzelinteresse",
    "Persönliche Erfahrung als Argument",
    "Kritik an der bisherigen Praxis",
    "Realistische Verbesserungsschritte",
]


@dataclass
class PartAudit:
    part_key: str
    generation_mode: str
    validation_notes: list[str] = field(default_factory=list)
    fallback_used: bool = False


@dataclass
class MockExamGenerationResult:
    items: list[ExerciseItem]
    variant_seed: str
    source_framework: str
    generator_version: str
    generation_mode: str
    calibration_notes: list[str] = field(default_factory=list)
    validation_notes: list[str] = field(default_factory=list)
    fallback_used: bool = False
    module_brief_used: bool = False
    llm_model: str | None = None
    mock_media_pack: list[MockMediaSegment] = field(default_factory=list)


@dataclass(frozen=True)
class GenerationProfile:
    llm_budget_sec: float
    module_brief_timeout_sec: int
    open_llm_timeout_sec: int
    open_llm_attempts: int


def _generation_profile(req: ExamGenerateRequest) -> GenerationProfile:
    if req.scope == "full":
        return GenerationProfile(
            llm_budget_sec=FULL_SCOPE_LLM_BUDGET_SEC,
            module_brief_timeout_sec=4,
            open_llm_timeout_sec=6,
            open_llm_attempts=1,
        )
    return GenerationProfile(
        llm_budget_sec=MODULE_SCOPE_LLM_BUDGET_SEC,
        module_brief_timeout_sec=6,
        open_llm_timeout_sec=8,
        open_llm_attempts=1,
    )


def _remaining_llm_budget(deadline: float | None) -> float:
    if deadline is None:
        return 999.0
    return max(0.0, deadline - monotonic())


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
    return result[:count] if result else [dict(topic_payload(None)) for _ in range(count)]


def _part_scenarios(level: str, module: str, part_count: int, topic: str | None, variant_seed: str) -> list[dict[str, Any]]:
    if topic:
        fixed = topic_payload(topic)
        return [dict(fixed) for _ in range(part_count)]
    pool = [dict(item) for item in GOETHE_MOCK_SCENARIOS.get(level, [])]
    return _expand_scenario_pool(pool, part_count, f"{level}:{module}:{variant_seed}")


def _distribute_points(total_points: int, slots: int) -> list[int]:
    if slots <= 0:
        return []
    base, remainder = divmod(total_points, slots)
    return [base + (1 if idx < remainder else 0) for idx in range(slots)]


def _ascii(value: str) -> str:
    return str(value or "").translate(_ASCII_TRANSLATION)


def _seed_key(*parts: str) -> str:
    return "::".join(parts)


def _stable_phrase(level: str, pool: list[str], seed_key: str) -> str:
    picked = stable_pick(pool, 1, f"{level}:{seed_key}")
    return picked[0] if picked else pool[0]


def _text_sentence_pack(level: str, scenario: dict[str, Any], blueprint: dict[str, Any], seed_key: str) -> list[str]:
    intro = _stable_phrase(level, INTRO_FRAMES[level], seed_key)
    follow = _stable_phrase(level, FOLLOW_UP_FRAMES[level], f"{seed_key}:follow")
    title = _ascii(str(scenario.get("title", "eine Alltagssituation")))
    setting = _ascii(str(scenario.get("setting", "einem neutralen Umfeld")))
    goal = _ascii(str(scenario.get("goal", "ein klares Ziel zu erreichen")))
    issue = _ascii(str(scenario.get("issue", "ein Hindernis auftaucht")))
    solution = _ascii(str(scenario.get("solution", "ein sinnvoller Loesungsweg entsteht")))
    person = _ascii(str(scenario.get("person", "eine Person")))
    context_bias = _ascii(str(blueprint.get("context_bias", "")))
    lexical_band = _ascii(str(blueprint.get("lexical_band", "")))
    hook = _ascii(str(scenario.get("hook", "")))
    sentences = [
        f"{intro} {title} im Kontext von {setting}.",
        f"{person} versucht dabei vor allem, {goal}.",
        f"{follow} zeigt sich, dass {issue}.",
        f"Als realistische Entwicklung wird beschrieben, dass {solution}.",
        f"Der Text bleibt pruefungsnah, {context_bias} und sprachlich {lexical_band}.",
    ]
    if hook:
        sentences.insert(1, f"Zentral ist dabei, dass {hook}.")
    return sentences


def _compose_source_text(level: str, scenario: dict[str, Any], blueprint: dict[str, Any], seed_key: str) -> tuple[str, str]:
    min_words, max_words = blueprint.get("text_length_range", (80, 180))
    title = f"{_ascii(str(scenario.get('title', 'Thema')))}"
    sentences = _text_sentence_pack(level, scenario, blueprint, seed_key)
    keywords = [_ascii(str(item)) for item in (scenario.get("keywords") or []) if str(item).strip()]
    item_focuses = [_ascii(str(item)) for item in (scenario.get("item_focuses") or []) if str(item).strip()]
    extras = [
        f"Im Detail wird erklaert, warum { _ascii(str(scenario.get('goal', 'ein Ziel verfolgt wird'))) }.",
        f"Mehrere Hinweise zeigen, dass { _ascii(str(scenario.get('issue', 'ein Problem entsteht'))) }.",
        f"Die Beteiligten beziehen sich auf { _ascii(str(scenario.get('setting', 'eine konkrete Situation'))) }.",
        f"Am Ende wirkt { _ascii(str(scenario.get('solution', 'eine Loesung moeglich ist'))) } am ueberzeugendsten.",
        f"Ein wichtiges Stichwort dabei ist { _ascii(str((scenario.get('keywords') or ['Alltag'])[0])) }.",
    ]
    extras.extend([f"Ein weiterer Aspekt betrifft das Stichwort {keyword}." for keyword in keywords[:6]])
    extras.extend([f"Ein kurzer Fokus liegt ausserdem auf {focus}." for focus in item_focuses[:8]])
    if not extras:
        extras.append("Der Grundtext bleibt eng an einer alltagsnahen Pruefungssituation.")
    text = " ".join(sentences)
    extra_index = 0
    while len(text.split()) < min_words:
        next_extra = extras[extra_index % len(extras)]
        text = f"{text} {next_extra}"
        extra_index += 1
    if len(text.split()) > max_words:
        words = text.split()
        text = " ".join(words[:max_words])
        if not text.endswith("."):
            text += "."
    return title, text


def _mock_playback_rate(level: str) -> float:
    rates = {
        "A1": 0.84,
        "A2": 0.88,
        "B1": 0.92,
        "B2": 0.95,
        "C1": 0.98,
        "C2": 1.0,
    }
    return rates.get(level, 0.95)


def _duration_hint_seconds(text: str, rate: float) -> int:
    words = max(1, len(text.split()))
    effective_rate = max(0.6, rate)
    return max(6, int((words / 2.55) / effective_rate))


def _matching_legend(blueprint: dict[str, Any], scenario: dict[str, Any], seed_key: str) -> list[dict[str, str]]:
    values = [str(value) for value in blueprint.get("choice_options", [])]
    if not values:
        return []
    source_type = str(blueprint.get("source_type", ""))
    goal = _ascii(str(scenario.get("goal", "")))
    issue = _ascii(str(scenario.get("issue", "")))
    solution = _ascii(str(scenario.get("solution", "")))
    setting = _ascii(str(scenario.get("setting", "")))
    person = _ascii(str(scenario.get("person", "")))
    labels: list[str]
    if source_type == "headings_bundle":
        labels = stable_pick(HEADING_BANK, len(values), f"{seed_key}:headings")
    elif source_type == "opinions_bundle":
        labels = [
            f"betont den Nutzen von {goal}",
            f"warnt davor, dass {issue}",
            f"unterstuetzt vor allem {solution}",
            f"ordnet die Lage in {setting} ein",
            f"verweist auf die Sicht von {person}",
            "fordert eine praktischere Organisation",
            "nimmt eine eher skeptische Position ein",
        ]
    elif "speaker" in str(blueprint.get("item_kind", "")):
        labels = [
            f"Sprecher {value}: Fokus auf {goal}" if value.lower() != "0" else "keine Zuordnung"
            for value in values
        ]
    else:
        labels = [
            f"Option {value}: Schwerpunkt {goal}" if value != "0" else "keine passende Option"
            for value in values
        ]
        if len(labels) > 1:
            labels[1] = f"Option {values[1]}: Problem {issue}"
        if len(labels) > 2:
            labels[2] = f"Option {values[2]}: Loesung {solution}"
        if len(labels) > 3:
            labels[3] = f"Option {values[3]}: Kontext {setting}"
    return [{"value": values[idx], "label": labels[idx % len(labels)]} for idx in range(len(values))]


def _objective_options(level: str, scenario: dict[str, Any], blueprint: dict[str, Any], item_number: int, seed_key: str) -> tuple[list[str], str]:
    goal = _ascii(str(scenario.get("goal", "")))
    issue = _ascii(str(scenario.get("issue", "")))
    solution = _ascii(str(scenario.get("solution", "")))
    setting = _ascii(str(scenario.get("setting", "")))
    title = _ascii(str(scenario.get("title", "")))
    person = _ascii(str(scenario.get("person", "")))
    source_type = str(blueprint.get("source_type", "article"))
    option_pool = [
        f"{person} verfolgt in erster Linie das Ziel, {goal}.",
        f"Im Zentrum steht das Problem, dass {issue}.",
        f"Am ueberzeugendsten wirkt der Vorschlag, {solution}.",
        f"Entscheidend ist der Kontext {setting}.",
        f"Das Thema {title} wird vor allem alltagsnah dargestellt.",
    ]
    if source_type in {"commentary", "article", "lecture_or_broadcast"}:
        option_pool.append("Der Text entwickelt eine klare Hauptthese und stuetzt sie mit Beispielen.")
    if level in {"C1", "C2"}:
        option_pool.append("Der Beitrag arbeitet mit einer differenzierten Gegenueberstellung mehrerer Perspektiven.")
    count = 4 if str(blueprint.get("item_kind")) == "mcq4" else 3
    ordered = stable_pick(option_pool, min(len(option_pool), count + 2), f"{seed_key}:mcq:{item_number}")
    options = ordered[:count]
    answer = options[item_number % len(options)]
    return options, answer


def _binary_statement(scenario: dict[str, Any], blueprint: dict[str, Any], item_number: int, seed_key: str) -> tuple[str, str]:
    truths = [
        f"{_ascii(str(scenario.get('person', 'Die Person')))} will vor allem {_ascii(str(scenario.get('goal', 'ein Ziel erreichen')))}.",
        f"Ein zentrales Problem ist, dass {_ascii(str(scenario.get('issue', 'eine Schwierigkeit entsteht')))}.",
        f"Als Loesung wird beschrieben, dass {_ascii(str(scenario.get('solution', 'eine Loesung moeglich ist')))}.",
    ]
    falsehoods = [
        f"{_ascii(str(scenario.get('person', 'Die Person')))} moechte die Situation komplett aufgeben.",
        "Im Text wird ausdruecklich gesagt, dass es gar kein Problem gibt.",
        "Die Beteiligten lehnen jede Loesung grundsaetzlich ab.",
    ]
    truth_first = stable_pick(["true", "false"], 1, f"{seed_key}:binary:{item_number}")[0]
    if truth_first == "true":
        statement = stable_pick(truths, 1, f"{seed_key}:truth:{item_number}")[0]
        answer = "Ja" if str(blueprint.get("item_kind")) == "yes_no" else "Richtig"
    else:
        statement = stable_pick(falsehoods, 1, f"{seed_key}:false:{item_number}")[0]
        answer = "Nein" if str(blueprint.get("item_kind")) == "yes_no" else "Falsch"
    return statement, answer


def _matching_prompt(choice_label: str, scenario: dict[str, Any], blueprint: dict[str, Any], item_number: int) -> str:
    source_type = str(blueprint.get("source_type", ""))
    goal = _ascii(str(scenario.get("goal", "")))
    issue = _ascii(str(scenario.get("issue", "")))
    title = _ascii(str(scenario.get("title", "")))
    if source_type == "headings_bundle":
        return f"Welche Ueberschrift passt am besten zur Aussage {item_number + 1} ueber {title}?"
    if "speaker" in str(blueprint.get("item_kind", "")):
        return f"Wem passt die Aussage {item_number + 1} am ehesten: Schwerpunkt auf {goal}?"
    return f"Welche Zuordnung passt zur Aussage {item_number + 1}, die sich auf {goal} und {issue} bezieht?"


def _build_objective_payload(level: str, module: str, part: dict[str, Any], scenario: dict[str, Any], blueprint: dict[str, Any], seed_key: str) -> dict[str, Any]:
    source_title, source_text = _compose_source_text(level, scenario, blueprint, seed_key)
    item_kind = str(blueprint.get("item_kind", "mcq3"))
    items: list[dict[str, Any]] = []
    legend = _matching_legend(blueprint, scenario, seed_key)
    options = [legend_item["value"] for legend_item in legend]
    item_focuses = [str(item).strip() for item in (scenario.get("item_focuses") or []) if str(item).strip()]
    for item_number in range(int(blueprint.get("item_count") or 1)):
        focus_label = item_focuses[item_number % len(item_focuses)] if item_focuses else _ascii(str(scenario.get("title", "diesem Text")))
        if item_kind in {"true_false", "yes_no"}:
            stem, answer = _binary_statement(scenario, blueprint, item_number, seed_key)
            items.append(
                {
                    "stem": f"{stem} Fokus: {focus_label}.",
                    "options": ["Ja", "Nein"] if item_kind == "yes_no" else ["Richtig", "Falsch"],
                    "answer": answer,
                    "explanation": f"Die Kernaussage passt zu {focus_label}.",
                }
            )
            continue
        if item_kind.startswith("matching"):
            answer = options[item_number % len(options)] if options else "A"
            choice_label = next((item["label"] for item in legend if item["value"] == answer), "")
            items.append(
                {
                    "stem": f"{_matching_prompt(choice_label, scenario, blueprint, item_number)} Fokus: {focus_label}.",
                    "options": options,
                    "answer": answer,
                    "explanation": f"{focus_label} passt zu {answer}: {choice_label}.",
                }
            )
            continue
        mcq_options, answer = _objective_options(level, scenario, blueprint, item_number, seed_key)
        items.append(
            {
                "stem": f"Welche Aussage trifft zu {focus_label} in Aufgabe {item_number + 1} zu?",
                "options": mcq_options,
                "answer": answer,
                "explanation": f"Die richtige Loesung greift {focus_label} auf.",
            }
        )
    return {
        "source_title": source_title,
        "source_text": source_text,
        "option_legend": legend,
        "items": items,
    }


def _leitpunkte(part: dict[str, Any], scenario: dict[str, Any], blueprint: dict[str, Any]) -> list[str]:
    source_type = str(blueprint.get("source_type", "message"))
    goal = _ascii(str(scenario.get("goal", "")))
    issue = _ascii(str(scenario.get("issue", "")))
    solution = _ascii(str(scenario.get("solution", "")))
    title = _ascii(str(scenario.get("title", "")))
    if source_type == "forum_post":
        return [
            f"Fuehren Sie in das Thema {title} ein.",
            f"Nehmen Sie klar Stellung zu {goal}.",
            "Begruenden Sie Ihre Meinung mit einem Beispiel oder einer Erfahrung.",
            f"Schliessen Sie mit einem realistischen Ausblick oder Vorschlag wie {solution}.",
        ]
    if source_type == "rewrite_task":
        return [
            "Formulieren Sie die markierten Passagen neu.",
            "Behalten Sie die Aussage des Ausgangstextes bei.",
            "Nutzen Sie die vorgegebenen Woerter grammatisch korrekt.",
        ]
    if source_type in {"presentation", "discussion", "planning_discussion"}:
        return [
            f"Greifen Sie das Thema {title} klar auf.",
            f"Entwickeln Sie Ihre Position zu {goal}.",
            f"Gehen Sie auf die Schwierigkeit ein, dass {issue}.",
            f"Arbeiten Sie auf eine sinnvolle Loesung wie {solution} hin.",
        ]
    return [
        f"Nennen Sie den Anlass oder das Problem: {issue}.",
        f"Formulieren Sie Ihr Ziel klar: {goal}.",
        f"Machen Sie mindestens einen konkreten Vorschlag: {solution}.",
        "Achten Sie auf ein zur Situation passendes Register.",
    ]


def _build_open_payload(level: str, module: str, part: dict[str, Any], scenario: dict[str, Any], blueprint: dict[str, Any], seed_key: str) -> dict[str, Any]:
    title = _ascii(str(scenario.get("title", "")))
    setting = _ascii(str(scenario.get("setting", "")))
    goal = _ascii(str(scenario.get("goal", "")))
    issue = _ascii(str(scenario.get("issue", "")))
    register = _ascii(str(blueprint.get("register", "")))
    min_words = int(part.get("min_words") or 0)
    expected_words = int(part.get("expected_words") or 0)
    task_label = _ascii(str(part.get("title", "Aufgabe")))
    response_style = _ascii(str(blueprint.get("response_style", "")))
    if module == "schreiben":
        prompt = (
            f"{task_label}: Verfassen Sie einen vollstaendigen, pruefungsnahen Text zu {title}. "
            f"Bleiben Sie im Register {register} und arbeiten Sie die Aufgabe adressatenorientiert aus."
        )
        situation = (
            f"Situation: {title} im Kontext {setting}. Sie muessen {goal} und zugleich mit der Schwierigkeit umgehen, "
            f"dass {issue}. Erwartet wird ein {response_style or 'kohärenter Text'} im Goethe-Rahmen."
        )
    elif module == "sprechen":
        prompt = (
            f"{task_label}: Reagieren Sie frei und pruefungsnah auf eine Sprechsituation zu {title}. "
            "Strukturieren Sie Ihre Aussagen, begruenden Sie Ihre Position und reagieren Sie auf Impulse."
        )
        situation = (
            f"Sprechsituation: {title} in {setting}. Ziel ist es, {goal}. "
            f"Ein zentraler Spannungs- oder Diskussionspunkt ist, dass {issue}. Register: {register}."
        )
    else:
        prompt = f"{task_label}: Bearbeiten Sie eine originelle, pruefungsnahe Situation zu {title} und reagieren Sie adressatenorientiert."
        situation = f"Situation: {title} in {setting}. Ziel: {goal}. Schwierigkeit: {issue}. Register: {register}."
    keywords = [
        _ascii(str(scenario.get("title", ""))),
        _ascii(str(scenario.get("goal", ""))),
        _ascii(str(scenario.get("issue", ""))),
        *[_ascii(str(item)) for item in (scenario.get("keywords") or [])[:3]],
    ]
    return {
        "prompt": prompt,
        "situation": situation,
        "leitpunkte": _leitpunkte(part, scenario, blueprint),
        "keywords": [word for word in keywords if word][:5],
        "answer_expectation": (
            (
                f"Goethe-orientierter Richtwert: mindestens {min_words} Woerter und klar erkennbare Bearbeitung aller Leitpunkte."
                if module == "schreiben"
                else f"Goethe-orientierter Richtwert: mindestens {min_words} Woerter."
            )
            if min_words
            else (
                "Goethe-orientierter Richtwert: frei sprechen, klar strukturieren und Rueckfragen aufgreifen."
                if module == "sprechen"
                else f"Goethe-orientierter Richtwert: circa {expected_words} Woerter."
            )
        ),
    }


def _llm_source_word_target(blueprint: dict[str, Any]) -> tuple[int, int]:
    min_words, max_words = blueprint.get("text_length_range", (0, 0))
    min_words = int(min_words or 0)
    max_words = int(max_words or 0)
    if not min_words and not max_words:
        return (0, 0)
    preferred_min = max(50, int(min_words * 0.62)) if min_words else max(50, int(max_words * 0.45))
    preferred_max = max(preferred_min + 24, int(max_words * 0.58)) if max_words else preferred_min + 36
    return (preferred_min, preferred_max)


def _llm_context_blob(part: dict[str, Any], scenario: dict[str, Any], blueprint: dict[str, Any]) -> str:
    preferred_min_words, preferred_max_words = _llm_source_word_target(blueprint)
    compact_blueprint = {
        "part_title": str(part.get("title", "")),
        "part_kind": blueprint.get("part_kind"),
        "item_kind": blueprint.get("item_kind"),
        "item_count": int(blueprint.get("item_count") or 1),
        "text_length_range": list(blueprint.get("text_length_range", (0, 0))),
        "preferred_source_words": [preferred_min_words, preferred_max_words],
        "register": blueprint.get("register"),
        "lexical_band": blueprint.get("lexical_band"),
        "syntax_band": blueprint.get("syntax_band"),
        "tone": blueprint.get("tone"),
        "response_style": blueprint.get("response_style"),
        "distractor_strategy": blueprint.get("distractor_strategy"),
        "response_format": blueprint.get("response_format"),
        "choice_options": blueprint.get("choice_options", []),
        "task_types": blueprint.get("task_types", []),
        "audio_plays": int(blueprint.get("audio_plays") or 0),
        "expected_words": int(blueprint.get("expected_words") or 0),
        "min_words": int(blueprint.get("min_words") or 0),
    }
    scenario_anchor = {
        "title": str(scenario.get("title", "")),
        "setting": str(scenario.get("setting", "")),
        "goal": str(scenario.get("goal", "")),
        "issue": str(scenario.get("issue", "")),
        "keywords": [str(item) for item in (scenario.get("keywords") or [])[:4]],
    }
    return json.dumps(
        {"blueprint": compact_blueprint, "scenario": scenario_anchor},
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _llm_token_budget(part: dict[str, Any], blueprint: dict[str, Any]) -> int:
    if blueprint.get("part_kind") == "open":
        expected_words = max(int(blueprint.get("expected_words") or 0), int(blueprint.get("min_words") or 0))
        return max(220, min(320, 180 + int(expected_words * 0.7)))

    item_count = int(blueprint.get("item_count") or 1)
    _, preferred_max_words = _llm_source_word_target(blueprint)
    anchor_words = max(70, preferred_max_words)
    budget = 120 + (item_count * 22) + int(anchor_words * 1.05)
    item_kind = str(blueprint.get("item_kind", ""))
    if item_kind in {"true_false", "yes_no"}:
        budget -= 20
    elif item_kind.startswith("matching"):
        budget += 40
    return max(300, min(720, budget))


def _objective_prompt_for_llm(level: str, module: str, part: dict[str, Any], scenario: dict[str, Any], blueprint: dict[str, Any]) -> str:
    options_note = ""
    if str(blueprint.get("item_kind", "")).startswith("matching"):
        options_note = f"Nutze diese festen Antwortwerte exakt: {blueprint.get('choice_options', [])}."
    elif str(blueprint.get("item_kind")) in {"true_false", "yes_no"}:
        options_note = f"Nutze nur diese festen Antwortwerte exakt: {blueprint.get('choice_options', []) or ['Richtig', 'Falsch']}."
    else:
        options_note = "Erzeuge pro Item kurze, klar unterscheidbare Optionen mit maximal sechs Woertern."
    return (
        "Erzeuge eine originale Goethe-inspirierte Pruefungsteil-Variante als kompaktes JSON.\n"
        f"Niveau: {level}\nModul: {module}\n"
        f"Kontext: {_llm_context_blob(part, scenario, blueprint)}\n"
        "Pflichten:\n"
        "- halte dich strikt an item_count\n"
        "- source_text muss natuerlich, originell und innerhalb preferred_source_words liegen\n"
        "- preferred_source_words ist absichtlich kompakter als text_length_range, aber lang genug fuer die Validierung\n"
        "- jedes Item braucht genau eine korrekte Antwort\n"
        f"- {options_note}\n"
        "- stem pro Item maximal 14 Woerter\n"
        "- explanation pro Item maximal 10 Woerter\n"
        "- keine Zusatzfelder, kein Markdown, keine offiziellen Originalformulierungen\n"
        "Schema:\n"
        "{"
        "\"source_title\":\"...\"," 
        "\"source_text\":\"...\"," 
        "\"option_legend\":[{\"value\":\"...\",\"label\":\"...\"}],"
        "\"items\":[{\"stem\":\"...\",\"options\":[\"...\"],\"answer\":\"...\",\"explanation\":\"...\"}]"
        "}"
    )


def _open_prompt_for_llm(level: str, module: str, part: dict[str, Any], scenario: dict[str, Any], blueprint: dict[str, Any]) -> str:
    return (
        "Erzeuge eine originale Goethe-inspirierte offene Aufgabe als kompaktes JSON.\n"
        f"Niveau: {level}\nModul: {module}\n"
        f"Kontext: {_llm_context_blob(part, scenario, blueprint)}\n"
        "Pflichten:\n"
        "- prompt und situation muessen pruefungsnah, konkret und originell sein\n"
        "- liefere 3 bis 5 klare Leitpunkte\n"
        "- liefere 4 bis 6 Keywords\n"
        "- answer_expectation kurz und ohne Zusatzkommentar\n"
        "- kein Markdown, keine Zusatzfelder, keine offiziellen Originalformulierungen\n"
        "Schema:\n"
        "{"
        "\"prompt\":\"...\"," 
        "\"situation\":\"...\"," 
        "\"leitpunkte\":[\"...\"],"
        "\"keywords\":[\"...\"],"
        "\"answer_expectation\":\"...\""
        "}"
    )


def _objective_brief_prompt_for_llm(level: str, module: str, part: dict[str, Any], scenario: dict[str, Any], blueprint: dict[str, Any]) -> str:
    item_count = int(blueprint.get("item_count") or 1)
    return (
        "Erzeuge ein kurzes kreatives Briefing als JSON fuer eine originale Goethe-inspirierte Teilaufgabe.\n"
        f"Niveau: {level}\nModul: {module}\n"
        f"Kontext: {_llm_context_blob(part, scenario, blueprint)}\n"
        "Pflichten:\n"
        "- source_title kurz und konkret\n"
        "- source_hook genau ein kompakter Satzteil\n"
        "- goal_variation, issue_variation und solution_variation jeweils kurz und natuerlich\n"
        f"- item_focuses genau {item_count} kurze Fokuslinien mit maximal sechs Woertern\n"
        "- keywords 4 bis 6 kurze Woerter\n"
        "- nur JSON, keine Zusatzfelder, keine offiziellen Originalformulierungen\n"
        "Schema:\n"
        "{"
        "\"source_title\":\"...\","
        "\"source_hook\":\"...\","
        "\"goal_variation\":\"...\","
        "\"issue_variation\":\"...\","
        "\"solution_variation\":\"...\","
        "\"item_focuses\":[\"...\"],"
        "\"keywords\":[\"...\"]"
        "}"
    )


def _should_use_llm_brief_strategy(blueprint: dict[str, Any]) -> bool:
    if blueprint.get("part_kind") == "open":
        return False
    item_count = int(blueprint.get("item_count") or 1)
    min_words, _ = blueprint.get("text_length_range", (0, 0))
    return item_count >= 6 or int(min_words or 0) >= 220


def _apply_objective_brief(scenario: dict[str, Any], brief: dict[str, Any], blueprint: dict[str, Any]) -> dict[str, Any]:
    item_count = int(blueprint.get("item_count") or 1)
    next_scenario = dict(scenario)
    source_title = str(brief.get("source_title", "")).strip()
    if source_title:
        next_scenario["title"] = source_title
    source_hook = str(brief.get("source_hook", "")).strip()
    if source_hook:
        next_scenario["hook"] = source_hook
    for brief_key, scenario_key in (
        ("goal_variation", "goal"),
        ("issue_variation", "issue"),
        ("solution_variation", "solution"),
    ):
        value = str(brief.get(brief_key, "")).strip()
        if value:
            next_scenario[scenario_key] = value
    focuses = [str(item).strip() for item in brief.get("item_focuses", []) if str(item).strip()]
    if focuses:
        next_scenario["item_focuses"] = focuses[:item_count]
    keywords = [str(item).strip() for item in brief.get("keywords", []) if str(item).strip()]
    if keywords:
        merged_keywords = []
        for keyword in [*keywords, *[str(item) for item in scenario.get("keywords", [])]]:
            cleaned = keyword.strip()
            if cleaned and cleaned not in merged_keywords:
                merged_keywords.append(cleaned)
        next_scenario["keywords"] = merged_keywords[:6]
    return next_scenario


def _module_brief_prompt_for_llm(level: str, module: str, parts: list[dict[str, Any]], scenarios: list[dict[str, Any]]) -> str:
    theme_bits = [
        f"{_ascii(str(scenario.get('title', 'Thema')))} in {_ascii(str(scenario.get('setting', 'einem Kontext')))}"
        for scenario in scenarios[: len(parts)]
    ]
    theme_summary = "; ".join(theme_bits[:4])
    return (
        "Antworte nur mit JSON dieses Schemas: "
        "{\"goal\":\"...\",\"issue\":\"...\",\"solution\":\"...\",\"keywords\":[\"...\"],\"part_focuses\":[\"...\"]}. "
        f"Thema: Goethe {level} {module}, {theme_summary}. "
        f"Genau {len(parts)} part_focuses. Jede Fokuslinie maximal vier Woerter. Genau vier keywords. Kurz, originell, nur deutsche Inhalte."
    )


def _generate_module_llm_brief(
    level: str,
    module: str,
    parts: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
    variant_seed: str,
    *,
    timeout_sec: int,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    prompt = _module_brief_prompt_for_llm(level, module, parts, scenarios)
    try:
        payload, model_name = generate_structured_exam_part(
            prompt,
            seed_key=f"{variant_seed}:{module}:module-brief",
            max_tokens=150,
            timeout_sec=timeout_sec,
        )
    except Exception as exc:
        return None, None, f"LLM-Modulbrief {module}: {exc}"
    if payload is None and model_name is None:
        return None, None, None
    if not isinstance(payload, dict):
        return None, None, f"LLM-Modulbrief {module}: ungueltiges JSON."

    compact = {
        "goal": str(payload.get("goal", "")).strip(),
        "issue": str(payload.get("issue", "")).strip(),
        "solution": str(payload.get("solution", "")).strip(),
        "keywords": [str(item).strip() for item in payload.get("keywords", []) if str(item).strip()],
        "part_focuses": [str(item).strip() for item in payload.get("part_focuses", []) if str(item).strip()],
    }
    if not any([compact["goal"], compact["issue"], compact["solution"], compact["keywords"], compact["part_focuses"]]):
        return None, None, f"LLM-Modulbrief {module}: leeres Briefing."
    return compact, model_name, None


def _apply_module_llm_brief(scenario: dict[str, Any], brief: dict[str, Any], part_index: int) -> dict[str, Any]:
    next_scenario = dict(scenario)
    for key in ("goal", "issue", "solution"):
        value = str(brief.get(key, "")).strip()
        if value:
            next_scenario[key] = value
    part_focuses = [str(item).strip() for item in brief.get("part_focuses", []) if str(item).strip()]
    if part_focuses:
        focus = part_focuses[min(part_index, len(part_focuses) - 1)]
        if focus:
            next_scenario["hook"] = focus
            next_scenario["item_focuses"] = [focus]
    keywords = [str(item).strip() for item in brief.get("keywords", []) if str(item).strip()]
    if keywords:
        merged_keywords = []
        for keyword in [*keywords, *[str(item) for item in scenario.get("keywords", [])]]:
            cleaned = keyword.strip()
            if cleaned and cleaned not in merged_keywords:
                merged_keywords.append(cleaned)
        next_scenario["keywords"] = merged_keywords[:6]
    return next_scenario


def _validate_payload(level: str, part: dict[str, Any], blueprint: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    if blueprint.get("part_kind") == "open":
        return validate_open_part_payload(level, part, blueprint, payload)
    return validate_objective_part_payload(level, part, blueprint, payload)


def _objective_item_type(item_kind: str) -> str:
    return "true_false" if item_kind in {"true_false", "yes_no"} else "mcq"


def _support_text(module: str, part: dict[str, Any], payload: dict[str, Any], blueprint: dict[str, Any]) -> str:
    base: list[str] = []
    if module == "hoeren":
        base.append(f"Mock-Hoerskript: {payload.get('source_title', part.get('title'))}")
    else:
        base.append(f"Grundtext: {payload.get('source_title', part.get('title'))}")
    source_text = str(payload.get("source_text", "")).strip()
    if source_text:
        base.append(source_text)
    legend = payload.get("option_legend", [])
    if isinstance(legend, list) and legend:
        base.append("Optionen / Zuordnungen:")
        base.extend([f"{item.get('value')}) {item.get('label')}" for item in legend if isinstance(item, dict)])
    if part.get("audio_plays"):
        base.append(f"Offizieller Hoerrahmen: {part['audio_plays']} Durchgang/Durchgaenge.")
    base.append(f"Kalibrierung: {blueprint.get('register')} · {blueprint.get('lexical_band')}.")
    return "\n".join(base)


def _normalize_objective_payload(
    *,
    level: str,
    module: str,
    part: dict[str, Any],
    blueprint: dict[str, Any],
    payload: dict[str, Any],
    points: list[int],
) -> list[ExerciseItem]:
    support = _support_text(module, part, payload, blueprint)
    item_kind = str(blueprint.get("item_kind", "mcq3"))
    items = payload.get("items", [])
    normalized: list[ExerciseItem] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        options = [str(option).strip() for option in item.get("options", []) if str(option).strip()]
        answer = str(item.get("answer", "")).strip()
        if not options:
            options = [answer] if answer else []
        normalized.append(
            ExerciseItem(
                id=f"{part['key']}_{index}",
                section=module,
                section_title=part["title"],
                prompt=str(item.get("stem", "")).strip(),
                support_text=support,
                item_type=_objective_item_type(item_kind),
                options=options,
                answer=answer,
                explanation=str(item.get("explanation", part["instructions"])).strip() or part["instructions"],
                points=points[index] if index < len(points) else 1,
                focus_tag=module,
            )
        )
    return normalized


def _build_mock_media_segment(level: str, module: str, part: dict[str, Any], payload: dict[str, Any]) -> MockMediaSegment | None:
    if module != "hoeren":
        return None
    script_text = str(payload.get("source_text", "")).strip()
    if not script_text:
        return None
    playback_rate = _mock_playback_rate(level)
    return MockMediaSegment(
        module=module,
        part_key=str(part["key"]),
        part_title=str(part["title"]),
        source_title=str(payload.get("source_title", part["title"])).strip() or str(part["title"]),
        script_text=script_text,
        audio_plays=max(1, int(part.get("audio_plays") or 1)),
        playback_rate=playback_rate,
        duration_hint_seconds=_duration_hint_seconds(script_text, playback_rate),
    )


def _normalize_open_payload(
    *,
    level: str,
    module: str,
    part: dict[str, Any],
    blueprint: dict[str, Any],
    payload: dict[str, Any],
    points: int,
) -> list[ExerciseItem]:
    leitpunkte = [str(point).strip() for point in payload.get("leitpunkte", []) if str(point).strip()]
    support_lines = [
        str(payload.get("situation", "")).strip(),
        "Leitpunkte:",
        *[f"- {point}" for point in leitpunkte],
    ]
    if payload.get("answer_expectation"):
        support_lines.append(str(payload.get("answer_expectation")).strip())
    support_lines.append(f"Kalibrierung: {blueprint.get('register')} · {blueprint.get('lexical_band')}.")
    keywords = [str(item).strip() for item in payload.get("keywords", []) if str(item).strip()]
    return [
        ExerciseItem(
            id=str(part["key"]),
            section=module,
            section_title=part["title"],
            prompt=str(payload.get("prompt", "")).strip(),
            support_text="\n".join([line for line in support_lines if line]),
            item_type="open",
            answer="freie Bearbeitung",
            explanation=f"Bewertet werden Aufgabenbezug, Register, Kohärenz und sprachliche Ausführung im Sinne der Goethe-Kriterien für {part['title']}.",
            points=points,
            keywords=keywords[:6],
            min_words=max(int(part.get("min_words") or 0), max(25, int(part.get("expected_words") or 0) // 2)),
            focus_tag=module,
        )
    ]


def _generate_part(
    *,
    level: str,
    module: str,
    part: dict[str, Any],
    scenario: dict[str, Any],
    blueprint: dict[str, Any],
    point_plan: list[int],
    seed_key: str,
    mock_audio_voice_gender: str | None = None,
    llm_module_assisted: bool = False,
    llm_deadline: float | None = None,
    open_llm_timeout_sec: int = 8,
    open_llm_attempts: int = 1,
) -> tuple[list[ExerciseItem], PartAudit, str | None, MockMediaSegment | None]:
    payload: dict[str, Any] | None = None
    llm_model: str | None = None
    validation_notes: list[str] = []
    used_fallback = False
    generation_mode = "deterministic_blueprint"

    if llm_module_assisted and blueprint.get("part_kind") != "open":
        payload = _build_objective_payload(level, module, part, scenario, blueprint, f"{seed_key}:module-brief")
        generation_mode = "hybrid_blueprint"
        validation_notes.extend([f"LLM-Modulbrief {part['key']}: {note}" for note in _validate_payload(level, part, blueprint, payload)])
    elif blueprint.get("part_kind") != "open":
        used_fallback = True
        payload = _build_objective_payload(level, module, part, scenario, blueprint, seed_key)
        validation_notes.extend([f"Fallback-Validierung {part['key']}: {note}" for note in _validate_payload(level, part, blueprint, payload)])

    if payload is None and blueprint.get("part_kind") == "open":
        llm_prompt = _open_prompt_for_llm(level, module, part, scenario, blueprint)
        llm_max_tokens = _llm_token_budget(part, blueprint)
    if payload is None and blueprint.get("part_kind") == "open" and _remaining_llm_budget(llm_deadline) < MIN_REMAINING_SEC_FOR_OPEN_LLM:
        validation_notes.append(
            f"LLM-Budget {part['key']}: Zeitbudget ausgeschöpft, produktive Aufgabe wird direkt aus dem validierten Blueprint erzeugt."
        )
    if payload is None and not (blueprint.get("part_kind") == "open" and _remaining_llm_budget(llm_deadline) < MIN_REMAINING_SEC_FOR_OPEN_LLM):
        repair_notes: list[str] = []
        max_attempts = max(1, int(open_llm_attempts if blueprint.get("part_kind") == "open" else MAX_GENERATION_ATTEMPTS))
        for attempt in range(max_attempts):
            attempt_prompt = llm_prompt
            if repair_notes:
                attempt_prompt = (
                    f"{llm_prompt}\n"
                    "Vermeide im neuen Versuch zwingend diese Probleme: "
                    + "; ".join(repair_notes[:4])
                )
            try:
                remaining_budget = _remaining_llm_budget(llm_deadline)
                timeout_sec = max(4, min(int(remaining_budget) if llm_deadline is not None else open_llm_timeout_sec, open_llm_timeout_sec))
                if llm_deadline is not None and remaining_budget < MIN_REMAINING_SEC_FOR_OPEN_LLM:
                    validation_notes.append(
                        f"LLM-Budget {part['key']}: Nach {attempt} Versuch(en) auf schnellen Blueprint-Fallback gewechselt."
                    )
                    break
                generated_payload, model_name = generate_structured_exam_part(
                    attempt_prompt,
                    seed_key=f"{seed_key}:attempt:{attempt}",
                    max_tokens=llm_max_tokens,
                    timeout_sec=timeout_sec,
                )
            except Exception as exc:
                generated_payload = None
                validation_notes.append(f"LLM-Ausfall {part['key']}: {exc}")
                model_name = None
            if generated_payload is None:
                break
            notes = _validate_payload(level, part, blueprint, generated_payload)
            if not notes:
                payload = generated_payload
                llm_model = model_name
                generation_mode = "llm_blueprint"
                break
            repair_notes = notes
            validation_notes.extend([f"LLM-Validierung {part['key']}: {note}" for note in notes])

    if payload is None:
        used_fallback = True
        if blueprint.get("part_kind") == "open":
            payload = _build_open_payload(level, module, part, scenario, blueprint, seed_key)
        else:
            payload = _build_objective_payload(level, module, part, scenario, blueprint, seed_key)
        validation_notes.extend([f"Fallback-Validierung {part['key']}: {note}" for note in _validate_payload(level, part, blueprint, payload)])

    if blueprint.get("part_kind") == "open":
        items = _normalize_open_payload(level=level, module=module, part=part, blueprint=blueprint, payload=payload, points=sum(point_plan))
    else:
        items = _normalize_objective_payload(level=level, module=module, part=part, blueprint=blueprint, payload=payload, points=point_plan)

    media_segment = _build_mock_media_segment(level, module, part, payload)
    if media_segment:
        try:
            media_segment = ensure_mock_audio_segment(media_segment, voice_gender_override=mock_audio_voice_gender if mock_audio_voice_gender in {"auto", "female", "male"} else None)
        except Exception as exc:
            validation_notes.append(f"Media-Pack {part['key']}: lokales Server-Audio fehlgeschlagen ({exc}).")
        if media_segment.audio_url:
            validation_notes.append(f"Media-Pack {part['key']}: lokales Server-Audio bereit.")
        else:
            validation_notes.append(f"Media-Pack {part['key']}: bereit fuer lokale Browser-Wiedergabe.")

    return (
        items,
        PartAudit(
            part_key=str(part["key"]),
            generation_mode=generation_mode,
            validation_notes=validation_notes,
            fallback_used=used_fallback,
        ),
        llm_model,
        media_segment,
    )


def _default_variant_seed(req: ExamGenerateRequest) -> str:
    return req.variant_seed or f"{req.level}:{req.scope}:{req.module}:blueprint-default"


def generate_goethe_mock_exam(req: ExamGenerateRequest, official: OfficialExamPayload) -> MockExamGenerationResult:
    modules = ["lesen", "hoeren", "schreiben", "sprechen"] if req.scope == "full" else [req.module]
    variant_seed = _default_variant_seed(req)
    generation_profile = _generation_profile(req)
    llm_deadline = monotonic() + generation_profile.llm_budget_sec
    items: list[ExerciseItem] = []
    audits: list[PartAudit] = []
    calibration_notes = [
        f"Blueprint-Version: {GOETHE_BLUEPRINT_VERSION}",
        "Originale Inhalte, an offizieller Struktur und Schwierigkeit kalibriert.",
        "Offizielle Materialien bleiben als Referenz getrennt sichtbar.",
        (
            f"Schnellprofil aktiv: {req.scope}-Mock mit LLM-Budget {int(generation_profile.llm_budget_sec)}s "
            "und validiertem Blueprint-Fallback."
        ),
    ]
    llm_models: set[str] = set()
    mock_media_pack: list[MockMediaSegment] = []
    module_brief_used = False

    for module in modules:
        module_def = _module_def(req.level, module)
        module_blueprints = [build_part_blueprint(req.level, module, part) for part in module_def["parts"]]
        scenarios = _part_scenarios(req.level, module, len(module_def["parts"]), req.topic, variant_seed)
        needs_module_brief = any(
            blueprint.get("part_kind") != "open" and _should_use_llm_brief_strategy(blueprint)
            for blueprint in module_blueprints
        )
        module_llm_brief = None
        module_llm_model = None
        module_llm_note = None
        if needs_module_brief and _remaining_llm_budget(llm_deadline) >= MIN_REMAINING_SEC_FOR_MODULE_BRIEF:
            module_llm_brief, module_llm_model, module_llm_note = _generate_module_llm_brief(
                req.level,
                module,
                module_def["parts"],
                scenarios,
                variant_seed,
                timeout_sec=min(generation_profile.module_brief_timeout_sec, max(4, int(_remaining_llm_budget(llm_deadline)))),
            )
        elif needs_module_brief:
            module_llm_note = (
                f"LLM-Modulbrief {module}: Zeitbudget zu knapp, Modul wird direkt aus dem Goethe-Blueprint aufgebaut."
            )
        if module_llm_model:
            llm_models.add(module_llm_model)
            calibration_notes.append(f"LLM-Modulbrief {module}: {module_llm_model}.")
            module_brief_used = True
        if module_llm_note:
            calibration_notes.append(module_llm_note)
        total_slots = sum(int(part.get("item_count") or 1) for part in module_def["parts"])
        point_plan = _distribute_points(int(module_def["scoring"]["max_points"]), total_slots)
        point_index = 0
        for part_index, part in enumerate(module_def["parts"]):
            blueprint = module_blueprints[part_index]
            part_slots = int(part.get("item_count") or 1)
            scenario = scenarios[min(part_index, len(scenarios) - 1)] if scenarios else dict(topic_payload(req.topic))
            if module_llm_brief:
                scenario = _apply_module_llm_brief(scenario, module_llm_brief, part_index)
            points = point_plan[point_index : point_index + part_slots] if blueprint.get("part_kind") != "open" else [sum(point_plan[point_index : point_index + part_slots])]
            point_index += part_slots
            part_items, audit, model_name, media_segment = _generate_part(
                level=req.level,
                module=module,
                part=part,
                scenario=scenario,
                blueprint=blueprint,
                point_plan=points,
                seed_key=_seed_key(req.level, module, str(part["key"]), variant_seed),
                mock_audio_voice_gender=req.mock_audio_voice_gender,
                llm_module_assisted=bool(module_llm_brief),
                llm_deadline=llm_deadline,
                open_llm_timeout_sec=generation_profile.open_llm_timeout_sec,
                open_llm_attempts=generation_profile.open_llm_attempts,
            )
            items.extend(part_items)
            audits.append(audit)
            if model_name:
                llm_models.add(model_name)
            if media_segment:
                mock_media_pack.append(media_segment)

    fallback_used = any(audit.fallback_used for audit in audits)
    generation_modes = {audit.generation_mode for audit in audits}
    if generation_modes == {"llm_blueprint"}:
        generation_mode = "llm_blueprint"
    elif generation_modes == {"deterministic_blueprint"}:
        generation_mode = "deterministic_blueprint"
    else:
        generation_mode = "hybrid_blueprint"
    validation_notes = [note for audit in audits for note in audit.validation_notes]
    source_framework = "Goethe blueprint + local LLM + validator"
    if generation_mode == "deterministic_blueprint":
        source_framework = "Goethe blueprint + deterministic validated fallback"
    if generation_mode == "hybrid_blueprint":
        source_framework = "Goethe blueprint + local LLM with validated fallback"
    if _remaining_llm_budget(llm_deadline) <= 0:
        calibration_notes.append("LLM-Zeitbudget vollständig ausgeschöpft; verbleibende Teile wurden sofort aus dem validierten Blueprint aufgebaut.")
    if llm_models:
        calibration_notes.append(f"Lokales Modell: {', '.join(sorted(llm_models))}")

    return MockExamGenerationResult(
        items=items,
        variant_seed=variant_seed,
        source_framework=source_framework,
        generator_version=GENERATOR_VERSION,
        generation_mode=generation_mode,
        calibration_notes=calibration_notes,
        validation_notes=validation_notes[:18],
        fallback_used=fallback_used,
        module_brief_used=module_brief_used,
        llm_model=", ".join(sorted(llm_models)) if llm_models else None,
        mock_media_pack=mock_media_pack,
    )
