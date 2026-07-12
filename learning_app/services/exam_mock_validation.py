from __future__ import annotations

import re
from typing import Any


GERMAN_TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß']+")

LEVEL_COMPLEXITY = {
    "A1": {"avg_word_max": 8.2, "sentence_words_max": 15, "min_words": 20},
    "A2": {"avg_word_max": 8.8, "sentence_words_max": 18, "min_words": 30},
    "B1": {"avg_word_max": 9.6, "sentence_words_max": 22, "min_words": 40},
    "B2": {"avg_word_max": 10.6, "sentence_words_max": 28, "min_words": 55},
    "C1": {"avg_word_max": 11.5, "sentence_words_max": 32, "min_words": 70},
    "C2": {"avg_word_max": 12.8, "sentence_words_max": 36, "min_words": 80},
}


def _tokens(text: str) -> list[str]:
    return GERMAN_TOKEN_RE.findall(text or "")


def _word_count(text: str) -> int:
    return len(_tokens(text))


def _avg_word_length(text: str) -> float:
    words = _tokens(text)
    if not words:
        return 0.0
    return sum(len(word) for word in words) / len(words)


def _sentence_word_max(text: str) -> int:
    segments = [segment.strip() for segment in re.split(r"[.!?]+", text or "") if segment.strip()]
    if not segments:
        return 0
    return max(_word_count(segment) for segment in segments)


def _validate_cefr_text(level: str, text: str) -> list[str]:
    if not text.strip():
        return ["Leerer Grundtext."]
    rules = LEVEL_COMPLEXITY.get(level, LEVEL_COMPLEXITY["B2"])
    notes: list[str] = []
    avg_length = _avg_word_length(text)
    sent_max = _sentence_word_max(text)
    total_words = _word_count(text)
    if total_words < int(rules["min_words"] * 0.7):
        notes.append("Grundtext fuer das Niveau zu kurz.")
    if avg_length > rules["avg_word_max"] + 1.6:
        notes.append("Lexikalische Dichte wirkt fuer das Niveau zu hoch.")
    if sent_max > rules["sentence_words_max"] + 10:
        notes.append("Satzlaenge wirkt fuer das Niveau oder die Teilaufgabe zu hoch.")
    return notes


def validate_objective_part_payload(level: str, part: dict[str, Any], blueprint: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    items = payload.get("items", [])
    if not isinstance(items, list):
        return ["Items muessen als Liste vorliegen."]
    expected_count = int(blueprint.get("item_count") or 1)
    if len(items) != expected_count:
        notes.append(f"Falsche Anzahl von Items: {len(items)} statt {expected_count}.")

    source_text = str(payload.get("source_text", "")).strip()
    min_words, max_words = blueprint.get("text_length_range", (0, 9999))
    word_count = _word_count(source_text)
    if word_count < int(min_words * 0.55):
        notes.append("Grundtext ist deutlich zu kurz.")
    if word_count > int(max_words * 1.2):
        notes.append("Grundtext ist deutlich zu lang.")
    notes.extend(_validate_cefr_text(level, source_text))

    seen_stems: set[str] = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            notes.append(f"Item {index} ist kein Objekt.")
            continue
        stem = str(item.get("stem", "")).strip()
        answer = str(item.get("answer", "")).strip()
        options = item.get("options", [])
        if not stem:
            notes.append(f"Item {index} ohne Fragestellung.")
        normalized_stem = stem.lower()
        if normalized_stem in seen_stems:
            notes.append(f"Item {index} wiederholt eine Fragestellung.")
        seen_stems.add(normalized_stem)

        if not isinstance(options, list) or not options:
            notes.append(f"Item {index} ohne Antwortoptionen.")
            continue
        normalized_options = [str(option).strip() for option in options if str(option).strip()]
        if len(set(option.lower() for option in normalized_options)) != len(normalized_options):
            notes.append(f"Item {index} enthaelt doppelte Optionen.")
        if answer not in normalized_options:
            notes.append(f"Item {index} referenziert keine gueltige richtige Antwort.")
        min_distinct = int(blueprint.get("validation_constraints", {}).get("min_distinct_options", 3))
        if len(normalized_options) < min_distinct:
            notes.append(f"Item {index} hat zu wenige differenzierte Optionen.")
    return notes


def validate_open_part_payload(level: str, part: dict[str, Any], blueprint: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    prompt = str(payload.get("prompt", "")).strip()
    situation = str(payload.get("situation", "")).strip()
    leitpunkte = payload.get("leitpunkte", [])
    keywords = payload.get("keywords", [])
    if not prompt:
        notes.append("Offene Aufgabe ohne Prompt.")
    if not situation:
        notes.append("Offene Aufgabe ohne situativen Kontext.")
    if not isinstance(leitpunkte, list) or len([point for point in leitpunkte if str(point).strip()]) < 2:
        notes.append("Offene Aufgabe ohne ausreichend Leitpunkte.")
    if not isinstance(keywords, list) or len([word for word in keywords if str(word).strip()]) < 3:
        notes.append("Offene Aufgabe ohne ausreichend Keywords.")
    combined = " ".join([prompt, situation, *[str(point) for point in leitpunkte]])
    notes.extend(_validate_cefr_text(level, combined))
    expected_words = int(part.get("expected_words") or 0)
    if expected_words and _word_count(combined) < max(28, int(expected_words * 0.2)):
        notes.append("Offene Aufgabe wirkt fuer den Zielumfang zu duenn beschrieben.")
    return notes
