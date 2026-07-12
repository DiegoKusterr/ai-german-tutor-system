from __future__ import annotations

from typing import Any

from .goethe_official import GOETHE_OFFICIAL_EXAMS

GOETHE_BLUEPRINT_VERSION = "goethe-blueprint-v2"

LEVEL_PROFILES = {
    "A1": {
        "lexical_band": "sehr alltagsnah, konkret, hochfrequent",
        "syntax_band": "kurze Hauptsaetze, sehr wenig Einbettung",
        "tone": "klar, freundlich, direkt",
        "context_bias": "Alltag, Orientierung, einfache Kontakte",
    },
    "A2": {
        "lexical_band": "alltagsnah, funktional, leicht erweitert",
        "syntax_band": "kurze bis mittlere Saetze, einfache Nebensaetze",
        "tone": "klar, sachlich, wenig abstrakt",
        "context_bias": "Alltag, Service, Wohnen, Arbeit, Verwaltung",
    },
    "B1": {
        "lexical_band": "alltagsnah bis gesellschaftlich, etwas variabler",
        "syntax_band": "mittlere Saetze, klare Konnektoren, stabile Nebensaetze",
        "tone": "natuerlich, sachlich, argumentativ einfach",
        "context_bias": "Arbeit, Bildung, Medien, Alltag, Nachbarschaft",
    },
    "B2": {
        "lexical_band": "differenziert, praezise, gesellschaftsnah",
        "syntax_band": "mittlere bis komplexe Satzgefuege, flexible Konnektoren",
        "tone": "pruefungsnah, sachlich, argumentativ",
        "context_bias": "Gesellschaft, Beruf, Bildung, Medien, Wissenschaft alltagsnah",
    },
    "C1": {
        "lexical_band": "abstrakter, nuancierter, bildungssprachlich kontrolliert",
        "syntax_band": "komplexe Satzgefuege, Verdichtung, klare argumentative Struktur",
        "tone": "praezise, analytisch, reif",
        "context_bias": "Gesellschaft, Kultur, Forschung, Fachkommunikation",
    },
    "C2": {
        "lexical_band": "hoch praezise, idiomatisch dosiert, textsortensicher",
        "syntax_band": "komplex, dicht, variabel, stilistisch kontrolliert",
        "tone": "souveraen, differenziert, textsortensensibel",
        "context_bias": "Feuilleton, Essay, Fachdebatte, Rezension, gehobene Diskussion",
    },
}


def _title_haystack(part: dict[str, Any]) -> str:
    return " ".join(
        [
            str(part.get("key", "")),
            str(part.get("title", "")),
            str(part.get("instructions", "")),
            str(part.get("response_format", "")),
        ]
    ).lower()


def _part_kind(module: str, part: dict[str, Any]) -> str:
    item_kind = str(part.get("item_kind", ""))
    if module in {"schreiben", "sprechen"}:
        return "open"
    if item_kind in {"true_false", "yes_no"}:
        return "binary"
    if item_kind.startswith("matching"):
        return "matching"
    if item_kind.startswith("mcq"):
        return "multiple_choice"
    return "objective"


def _source_type(module: str, part: dict[str, Any]) -> str:
    haystack = _title_haystack(part)
    if module == "lesen":
        if "korrespondenz" in haystack or "e-mail" in haystack or "nachricht" in haystack:
            return "message"
        if "anzeig" in haystack or "angebot" in haystack or "orientierung" in haystack:
            return "classifieds"
        if "ueberschrift" in haystack or "überschrift" in haystack:
            return "headings_bundle"
        if "standpunkte" in haystack or "positionen" in haystack or "meinungen" in haystack:
            return "opinions_bundle"
        if "lueckentext" in haystack or "lückentext" in haystack:
            return "gapped_article"
        if "rekonstruktion" in haystack:
            return "reconstruction"
        if "kommentar" in haystack:
            return "commentary"
        if "reportage" in haystack:
            return "reportage"
        return "article"
    if module == "hoeren":
        if "podcast" in haystack:
            return "podcast"
        if "interview" in haystack:
            return "interview"
        if "diskussion" in haystack or "mehreren personen" in haystack:
            return "panel_discussion"
        if "vortrag" in haystack or "radio" in haystack:
            return "lecture_or_broadcast"
        if "gespraech" in haystack or "gespräch" in haystack:
            return "dialogue"
        return "audio_segments"
    if module == "schreiben":
        if "forum" in haystack or "diskussionsbeitrag" in haystack:
            return "forum_post"
        if "beschwerde" in haystack:
            return "complaint"
        if "leserbrief" in haystack:
            return "letter_to_editor"
        if "buchbesprechung" in haystack:
            return "review"
        if "formular" in haystack:
            return "form"
        if "kurzreferat" in haystack or "ueberarbeiten" in haystack or "überarbeiten" in haystack:
            return "rewrite_task"
        return "message"
    if "planung" in haystack or "planen" in haystack:
        return "planning_discussion"
    if "vortrag" in haystack or "praesentation" in haystack or "präsentation" in haystack or "produktion" in haystack:
        return "presentation"
    return "discussion"


def _register(module: str, level: str, part: dict[str, Any]) -> str:
    haystack = _title_haystack(part)
    if module == "schreiben":
        if "forum" in haystack or "diskussionsbeitrag" in haystack:
            return "halboeffentlich argumentativ"
        if "nachricht" in haystack or "e-mail" in haystack:
            return "adressatenorientiert, alltagsnah bis halb formell"
        if "beschwerde" in haystack or "leserbrief" in haystack:
            return "formell bis halb formell"
        if "buchbesprechung" in haystack:
            return "rezensierend, reflektiert"
        if "formular" in haystack:
            return "funktional, knapp"
    if module == "sprechen":
        if "vortrag" in haystack or "praesentation" in haystack or "präsentation" in haystack:
            return "gegliedert, frei gesprochen, pruefungsnah"
        if "diskussion" in haystack:
            return "argumentativ, interaktiv"
        return "kooperativ, dialogisch"
    return "sachlich pruefungsnah"


def _text_length_range(level: str, module: str, part: dict[str, Any]) -> tuple[int, int]:
    expected_words = int(part.get("expected_words") or 0)
    item_count = int(part.get("item_count") or 1)
    if module == "schreiben":
        if expected_words:
            return (max(20, int(expected_words * 0.82)), max(40, int(expected_words * 1.18)))
        defaults = {"A1": (25, 45), "A2": (35, 60), "B1": (80, 130), "B2": (110, 180), "C1": (180, 280), "C2": (280, 420)}
        return defaults[level]
    if module == "sprechen":
        if expected_words:
            return (max(20, int(expected_words * 0.75)), max(40, int(expected_words * 1.15)))
        defaults = {"A1": (20, 40), "A2": (35, 65), "B1": (60, 110), "B2": (90, 150), "C1": (140, 220), "C2": (160, 260)}
        return defaults[level]
    per_item = {"A1": 30, "A2": 36, "B1": 48, "B2": 60, "C1": 70, "C2": 82}[level]
    if _source_type(module, part) in {"article", "commentary", "reportage", "lecture_or_broadcast"}:
        per_item += 12
    if _source_type(module, part) in {"classifieds", "headings_bundle", "opinions_bundle"}:
        per_item = max(26, per_item - 10)
    minimum = max(70, int(item_count * per_item * 0.65))
    maximum = max(minimum + 40, int(item_count * per_item * 1.05))
    return (minimum, maximum)


def _distractor_strategy(module: str, part: dict[str, Any]) -> str:
    item_kind = str(part.get("item_kind", ""))
    source_type = _source_type(module, part)
    if item_kind in {"true_false", "yes_no"}:
        return "near-miss factual inversion"
    if item_kind.startswith("matching"):
        if source_type in {"headings_bundle", "opinions_bundle"}:
            return "stance and nuance confusion"
        if source_type in {"classifieds", "reconstruction"}:
            return "detail-overlap and fit confusion"
        return "role and detail confusion"
    if item_kind == "mcq4":
        return "high-plausibility semantic contrast"
    return "single-best-answer with close semantic distractors"


def _response_style(module: str, part: dict[str, Any]) -> str:
    kind = _part_kind(module, part)
    if kind == "open":
        return "sustained production"
    if kind == "binary":
        return "binary judgement"
    if kind == "matching":
        return "mapping"
    return "single choice"


def build_part_blueprint(level: str, module: str, part: dict[str, Any]) -> dict[str, Any]:
    if level not in GOETHE_OFFICIAL_EXAMS:
        raise KeyError(f"Unbekanntes Goethe-Niveau: {level}")
    profile = LEVEL_PROFILES[level]
    return {
        "blueprint_version": GOETHE_BLUEPRINT_VERSION,
        "level": level,
        "module": module,
        "part_key": str(part.get("key")),
        "part_title": str(part.get("title")),
        "part_kind": _part_kind(module, part),
        "source_type": _source_type(module, part),
        "register": _register(module, level, part),
        "lexical_band": profile["lexical_band"],
        "syntax_band": profile["syntax_band"],
        "tone": profile["tone"],
        "context_bias": profile["context_bias"],
        "response_style": _response_style(module, part),
        "distractor_strategy": _distractor_strategy(module, part),
        "text_length_range": _text_length_range(level, module, part),
        "item_count": int(part.get("item_count") or 1),
        "expected_words": int(part.get("expected_words") or 0),
        "min_words": int(part.get("min_words") or 0),
        "audio_plays": int(part.get("audio_plays") or 0),
        "response_format": str(part.get("response_format") or ""),
        "choice_options": [str(option) for option in part.get("choice_options", [])],
        "item_kind": str(part.get("item_kind", "")),
        "task_types": [str(task_type) for task_type in part.get("task_types", [])],
        "validation_constraints": {
            "require_single_correct_answer": _part_kind(module, part) in {"binary", "matching", "multiple_choice"},
            "max_repeated_tokens": 10 if level in {"A1", "A2"} else 14,
            "min_distinct_options": 2 if _part_kind(module, part) == "binary" else 3,
            "allow_audio_scaffold_only": module == "hoeren",
        },
    }


def get_module_generation_blueprints(level: str, module: str) -> list[dict[str, Any]]:
    module_def = GOETHE_OFFICIAL_EXAMS[level]["modules"][module]
    return [build_part_blueprint(level, module, part) for part in module_def["parts"]]


def get_all_module_generation_blueprints(level: str) -> dict[str, list[dict[str, Any]]]:
    return {
        module_key: get_module_generation_blueprints(level, module_key)
        for module_key in GOETHE_OFFICIAL_EXAMS[level]["modules"]
    }
