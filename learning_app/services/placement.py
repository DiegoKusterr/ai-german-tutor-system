from __future__ import annotations

from collections import defaultdict

from ..db import connection_scope
from ..schemas import (
    ExerciseItem,
    ExerciseResultItem,
    PlacementHistoryItem,
    PlacementResultPayload,
    PlacementSkillEstimate,
    PlacementStartPayload,
    PlacementStartRequest,
    PlacementSubmitRequest,
)
from .common import (
    build_error_insight,
    build_study_plan,
    compute_open_score,
    level_from_percent,
    make_id,
    objective_match,
    save_attempt,
    save_exercise,
    split_words,
    to_json,
    utc_now_iso,
)


def _placement_items() -> list[ExerciseItem]:
    return [
        ExerciseItem(id="pl_read_1", section="lesen", section_title="Lesen", prompt="Sie lesen auf dem Aushang: 'Der Kursraum wurde wegen Renovierungsarbeiten in Raum 2.14 verlegt.' Wohin müssen Sie gehen?", item_type="mcq", options=["in Raum 2.14", "in die Bibliothek", "zum Sekretariat", "nach Hause"], answer="in Raum 2.14", explanation="`verlegt` zeigt, dass der Kursraum gewechselt wurde.", points=2, focus_tag="lesen"),
        ExerciseItem(id="pl_read_2", section="lesen", section_title="Lesen", prompt="Welche Aussage passt? 'Die Teilnehmer sollen den Bericht bis Freitag einreichen, damit er vor dem Wochenende geprüft werden kann.'", item_type="mcq", options=["Der Bericht ist nur freiwillig.", "Der Bericht muss vor Freitag geprüft werden.", "Der Bericht soll spätestens Freitag abgegeben werden.", "Das Wochenende beginnt am Freitag."], answer="Der Bericht soll spätestens Freitag abgegeben werden.", explanation="Entscheidend ist die Formulierung `bis Freitag einreichen`.", points=2, focus_tag="lesen"),
        ExerciseItem(id="pl_listen_1", section="hoeren", section_title="Hören (Transkript)", support_text="Transkript: 'Guten Tag. Der Zug nach Köln fährt heute nicht von Gleis 4, sondern ausnahmsweise von Gleis 7. Bitte achten Sie auf die Lautsprecherdurchsagen.'", prompt="Von welchem Gleis fährt der Zug heute ab?", item_type="short", answer="Gleis 7", explanation="Die Ansage korrigiert Gleis 4 auf Gleis 7.", points=2, focus_tag="hoeren"),
        ExerciseItem(id="pl_listen_2", section="hoeren", section_title="Hören (Transkript)", support_text="Transkript: 'Wenn Sie sich online anmelden, sparen Sie zehn Euro. Die Anmeldung im Büro ist aber bis Donnerstag möglich.'", prompt="Was ist der Vorteil der Online-Anmeldung?", item_type="short", answer="Man spart zehn Euro", explanation="Der Vorteil wird ausdrücklich genannt.", points=2, focus_tag="hoeren"),
        ExerciseItem(id="pl_grammar_1", section="grammatik", section_title="Grammatik", prompt="Er kommt später, ___ er noch einen Termin hat.", item_type="fill_blank", answer="weil", explanation="Hier wird ein Kausalsatz mit `weil` gebraucht.", points=2, focus_tag="grammatik"),
        ExerciseItem(id="pl_grammar_2", section="grammatik", section_title="Grammatik", prompt="Wir warten ___ den Bus.", item_type="fill_blank", answer="auf", explanation="`warten auf` verlangt Akkusativ.", points=2, focus_tag="grammatik"),
        ExerciseItem(id="pl_grammar_3", section="grammatik", section_title="Grammatik", prompt="Wenn ich mehr Zeit hätte, ___ ich einen Intensivkurs machen.", item_type="fill_blank", answer="würde", explanation="Hier steht Konjunktiv II mit `würde`.", points=2, focus_tag="grammatik"),
        ExerciseItem(id="pl_vocab_1", section="wortschatz", section_title="Wortschatz", prompt="Welches Wort passt am besten zu `Bewerbungsgespräch`?", item_type="mcq", options=["Vorstellungsgespräch", "Verspätung", "Mietvertrag", "Speisekarte"], answer="Vorstellungsgespräch", explanation="Beide Ausdrücke bezeichnen in diesem Kontext dasselbe.", points=2, focus_tag="wortschatz"),
        ExerciseItem(id="pl_vocab_2", section="wortschatz", section_title="Wortschatz", prompt="Welches Verb passt am besten? `eine Entscheidung ...`", item_type="mcq", options=["machen", "treffen", "nehmen", "bekommen"], answer="treffen", explanation="Die übliche Kollokation ist `eine Entscheidung treffen`.", points=2, focus_tag="wortschatz"),
        ExerciseItem(id="pl_write_1", section="schreiben", section_title="Schreiben", prompt="Schreiben Sie 60-90 Wörter: Sie können heute nicht zum Deutschkurs kommen. Erklären Sie den Grund, entschuldigen Sie sich und schlagen Sie einen neuen Termin vor.", item_type="open", answer="grund entschuldigung neuer termin", explanation="Die Aufgabe verlangt Grund, Entschuldigung und Terminvorschlag.", points=8, min_words=60, keywords=["heute", "leider", "Entschuldigung", "neuer Termin"], focus_tag="schreiben"),
        ExerciseItem(id="pl_speak_1", section="sprechen", section_title="Sprechen (Textantwort)", prompt="Antworten Sie in 50-80 Wörtern: Welches Lernziel haben Sie für Deutsch und wie wollen Sie es erreichen?", item_type="open", answer="ziel plan praxis", explanation="Gefragt sind Lernziel, Motivation und konkreter Lernplan.", points=8, min_words=50, keywords=["lernen", "Deutsch", "Ziel", "üben"], focus_tag="sprechen"),
    ]


def start_placement(req: PlacementStartRequest) -> PlacementStartPayload:
    now = utc_now_iso()
    session_id = make_id("placement")
    payload = PlacementStartPayload(
        session_id=session_id,
        title="Goethe-orientierter Einstufungstest",
        instructions="Bearbeiten Sie die Aufgaben ohne Hilfsmittel. Die Diagnose deckt Lesen, Hören als Transkript, Grammatik, Wortschatz, Schreiben und textbasiertes Sprechen ab.",
        goal_exam=req.goal_exam,
        items=_placement_items(),
        official_note="Dies ist kein offizieller Goethe-Einstufungstest, sondern eine strukturierte In-App-Diagnose auf CEFR-Basis.",
    )
    with connection_scope() as conn:
        conn.execute(
            """
            INSERT INTO placement_sessions (id, level_hint, goal_exam, title, state_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, req.level_hint, req.goal_exam, payload.title, to_json(payload.model_dump()), now, now),
        )
    save_exercise(
        exercise_id=session_id,
        category="placement",
        module="diagnostic",
        level=req.level_hint or "A2",
        title=payload.title,
        prompt_payload=payload.model_dump(),
        answer_payload={"items": [item.model_dump() for item in payload.items]},
        criteria_payload=["placement", "cefr", "diagnostic"],
        meta_payload={"goal_exam": req.goal_exam},
    )
    return payload


def _skill_summary(skill: str, percent: float) -> str:
    descriptions = {
        "lesen": "Leseverstehen und gezielte Informationsentnahme",
        "hoeren": "Hörverstehen und Erkennen relevanter Details",
        "grammatik": "Kontrolle von Strukturen und Formen",
        "wortschatz": "lexikalische Präzision und Kollokationen",
        "schreiben": "schriftliche Aufgabenbewältigung mit Struktur und Register",
        "sprechen": "mündliche Entwicklung, Zielorientierung und Reaktion",
    }
    return f"{descriptions.get(skill, skill)} bei ungefähr {percent:.0f}%."


def submit_placement(req: PlacementSubmitRequest) -> PlacementResultPayload:
    with connection_scope() as conn:
        row = conn.execute("SELECT * FROM placement_sessions WHERE id = ?", (req.session_id,)).fetchone()
    if not row:
        raise ValueError("Einstufungssitzung nicht gefunden.")

    payload = PlacementStartPayload.model_validate_json(row["state_json"])
    by_skill_score: dict[str, float] = defaultdict(float)
    by_skill_max: dict[str, float] = defaultdict(float)
    results: list[ExerciseResultItem] = []
    weaknesses: list[str] = []

    for item in payload.items:
        user_answer = req.answers.get(item.id, "").strip()
        if item.item_type in {"mcq", "short", "fill_blank"}:
            ratio, feedback = objective_match(user_answer, item.answer)
            score = round(item.points * ratio, 2)
            corrected = item.answer if score < item.points else None
            errors = [] if score == item.points else [build_error_insight("grammatik" if item.section == "grammatik" else "wortschatz", item.prompt)]
        else:
            score, hints = compute_open_score(user_answer, keywords=item.keywords, max_score=item.points, min_words=item.min_words or 40)
            feedback = " ".join(hints) if hints else "Die Antwort ist für diesen Teil ausreichend entwickelt."
            corrected = user_answer if user_answer.endswith(".") else f"{user_answer}."
            errors = []
            if len(split_words(user_answer)) < item.min_words:
                errors.append(build_error_insight("aufgabenbezug", item.prompt))
            if "weil" in user_answer and ", weil " not in user_answer:
                errors.append(build_error_insight("wortstellung", user_answer))
        results.append(ExerciseResultItem(item_id=item.id, prompt=item.prompt, user_answer=user_answer, expected_answer=item.answer, score=score, max_score=item.points, feedback=feedback, corrected_version=corrected, error_tags=errors))
        by_skill_score[item.section or "general"] += score
        by_skill_max[item.section or "general"] += item.points
        if score < item.points * 0.6:
            weaknesses.append(item.section or "general")

    skill_estimates: list[PlacementSkillEstimate] = []
    overall_numerator = 0.0
    overall_denominator = 0.0
    for skill, score in by_skill_score.items():
        max_score = by_skill_max[skill]
        percent = round((score / max_score) * 100, 1) if max_score else 0.0
        level = level_from_percent(percent)
        confidence = round(min(0.95, 0.55 + (max_score / 20)), 2)
        skill_estimates.append(PlacementSkillEstimate(skill=skill, level=level, confidence=confidence, percent=percent, summary=_skill_summary(skill, percent)))
        overall_numerator += score
        overall_denominator += max_score

    overall_percent = round((overall_numerator / overall_denominator) * 100, 1) if overall_denominator else 0.0
    overall_level = level_from_percent(overall_percent)
    recommended_exam = f"goethe_{overall_level.lower()}"
    strengths = [f"{item.skill}: {item.level}" for item in sorted(skill_estimates, key=lambda current: current.percent, reverse=True)[:3]]
    weak_skills = [item.skill for item in sorted(skill_estimates, key=lambda current: current.percent)[:3]]
    gaps = [f"Bauen Sie {skill} mit gezielter Praxis weiter aus." for skill in weak_skills]
    next_level_requirements = [f"Für den Sprung über {overall_level} hinaus brauchen Sie mehr Stabilität in {skill}." for skill in weak_skills]
    roadmap_preview = build_study_plan(weaknesses or ["wortschatz", "grammatik"], recommended_exam)
    created_at = utc_now_iso()
    result_payload = PlacementResultPayload(
        session_id=req.session_id,
        overall_level=overall_level,
        confidence=round(min(0.95, 0.6 + overall_percent / 300), 2),
        recommended_exam=recommended_exam,
        strengths=strengths,
        gaps=gaps,
        next_level_requirements=next_level_requirements,
        skill_estimates=skill_estimates,
        roadmap_preview=roadmap_preview,
        results=results,
        created_at=created_at,
    )

    with connection_scope() as conn:
        conn.execute("UPDATE placement_sessions SET result_json = ?, updated_at = ? WHERE id = ?", (result_payload.model_dump_json(), created_at, req.session_id))

    save_attempt(
        exercise_id=req.session_id,
        category="placement",
        module="diagnostic",
        level=overall_level,
        user_answers=req.answers,
        score=overall_numerator,
        max_score=overall_denominator,
        percent=overall_percent,
        feedback_payload=result_payload.model_dump(),
        corrected_payload={"overall_level": overall_level},
        error_tags_payload=[build_error_insight(skill, skill).model_dump() for skill in weak_skills],
    )
    return result_payload


def list_placement_history() -> list[PlacementHistoryItem]:
    with connection_scope() as conn:
        rows = conn.execute(
            """
            SELECT id, result_json, created_at
            FROM placement_sessions
            WHERE result_json IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 20
            """
        ).fetchall()
    history: list[PlacementHistoryItem] = []
    for row in rows:
        result = PlacementResultPayload.model_validate_json(row["result_json"])
        history.append(PlacementHistoryItem(session_id=row["id"], overall_level=result.overall_level, confidence=result.confidence, created_at=row["created_at"], recommended_exam=result.recommended_exam))
    return history
