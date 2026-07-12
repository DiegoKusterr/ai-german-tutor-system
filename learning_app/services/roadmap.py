from __future__ import annotations

import json
from typing import Any

from ..db import connection_scope
from ..learning_materials import GOAL_EXAM_LABELS, ROADMAP_KNOWLEDGE
from ..schemas import RoadmapActivateRequest, RoadmapGenerateRequest, RoadmapMilestone, RoadmapPayload, RoadmapWeek
from .common import current_recommendation_strategy, make_id, next_level, save_recommendation_event, utc_now_iso


def _resolve_current_level(req: RoadmapGenerateRequest) -> str:
    if req.current_level:
        return req.current_level
    if req.placement_session_id:
        with connection_scope() as conn:
            row = conn.execute("SELECT result_json FROM placement_sessions WHERE id = ?", (req.placement_session_id,)).fetchone()
        if row and row["result_json"]:
            from ..schemas import PlacementResultPayload

            return PlacementResultPayload.model_validate_json(row["result_json"]).overall_level
    return "A2"


def _roadmap_title(current_level: str, target_level: str) -> str:
    return f"Lernplan {current_level} → {target_level}"


def _roadmap_summary(current_level: str, target_level: str, target_exam: str) -> str:
    target_label = GOAL_EXAM_LABELS.get(target_exam, target_exam)
    return (
        f"Dieser Lernplan führt von {current_level} zu {target_level} mit Fokus auf {target_label}. "
        "Sie verbindet Grammatik, Wortschatz, produktive Fertigkeiten und prüfungsnahe Simulation."
    )


def _normalize_legacy_roadmap_copy(row: Any) -> tuple[str, str, bool]:
    title = str(row["title"] or "")
    summary = str(row["summary"] or "")
    changed = False

    if title.startswith("Roadmap "):
        title = _roadmap_title(str(row["current_level"]), str(row["target_level"]))
        changed = True

    if summary.startswith("Diese Roadmap führt"):
        summary = _roadmap_summary(str(row["current_level"]), str(row["target_level"]), str(row["target_exam"]))
        changed = True

    return title, summary, changed


def _roadmap_weeks(current_level: str, target_level: str, weeks: int, target_exam: str) -> list[RoadmapWeek]:
    must_know = ROADMAP_KNOWLEDGE.get(target_level, ROADMAP_KNOWLEDGE["B2"])
    exam_label = GOAL_EXAM_LABELS.get(target_exam, target_exam)
    plan: list[RoadmapWeek] = []
    for week in range(1, weeks + 1):
        must_know_item = must_know[(week - 1) % len(must_know)]
        progress_ratio = week / max(weeks, 1)
        if progress_ratio <= 0.34:
            title = "Fundament und Genauigkeit"
            focus = "Stabilisieren Sie Kernstrukturen, Aufgabenverständnis und saubere Standardsätze."
            skills = ["grammatik", "lesen"]
            exam_task = "Arbeiten Sie einen kurzen Modulblock langsam und kontrolliert durch."
        elif progress_ratio <= 0.74:
            title = "Transfer und produktive Sicherheit"
            focus = "Verbinden Sie Grammatik, Wortschatz und Produktion mit klarer Struktur und Rückmeldeschleife."
            skills = ["schreiben", "sprechen"]
            exam_task = "Planen Sie mindestens eine produktive Einheit mit anschließender Selbstkorrektur und einer zweiten verbesserten Version."
        else:
            title = "Prüfungsroutine und Endspurt"
            focus = "Trainieren Sie unter Realbedingungen und schließen Sie Lücken nur noch gezielt."
            skills = ["lesen", "hoeren", "schreiben", "sprechen"]
            exam_task = f"Bearbeiten Sie jetzt eine vollständige {exam_label}-Simulation unter Zeitdruck oder mindestens zwei Module am Stück."
        plan.append(
            RoadmapWeek(
                week=week,
                title=title,
                focus=focus,
                tasks=[
                    f"Studieren Sie diese Woche gezielt: {must_know_item}.",
                    exam_task,
                    "Führen Sie ein Fehlerprotokoll und wiederholen Sie nur die zwei häufigsten Fehlertypen aus Ihren letzten Versuchen.",
                ],
                checkpoint=f"Am Ende von Woche {week}: kurze Selbstprüfung zu {must_know_item} plus klare Entscheidung, welches Modul in Woche {week + 1 if week < weeks else week} Vorrang hat.",
                linked_skills=skills,
            )
        )
    return plan


def _fixed_path_weeks(target_level: str, weeks: int, target_exam: str) -> list[RoadmapWeek]:
    exam_label = GOAL_EXAM_LABELS.get(target_exam, target_exam)
    module_sequence = ["lesen", "hoeren", "schreiben", "sprechen"]
    module_labels = {
        "lesen": "Lesen",
        "hoeren": "Hören",
        "schreiben": "Schreiben",
        "sprechen": "Sprechen",
    }
    plan: list[RoadmapWeek] = []
    for week in range(1, weeks + 1):
        module = module_sequence[(week - 1) % len(module_sequence)]
        module_label = module_labels[module]
        full_mock_week = week % len(module_sequence) == 0 or week == weeks
        plan.append(
            RoadmapWeek(
                week=week,
                title=f"Fester Vergleichsblock: {module_label}",
                focus="Nicht-personalisierte Vergleichsbedingung mit fester Modulreihenfolge.",
                tasks=[
                    f"Wiederholen Sie in dieser Woche einen festen Kernpunkt auf Zielniveau {target_level}.",
                    f"Bearbeiten Sie das Modul {module_label} in der vorgegebenen Reihenfolge und protokollieren Sie nur Zeit, Prozentwert und kurze Selbstnotiz.",
                    (
                        f"Führen Sie zusätzlich eine vollständige {exam_label}-Simulation als festen Zykluspunkt durch."
                        if full_mock_week
                        else "Ergänzen Sie zum Abschluss 15 Minuten Vokabel- oder Strukturenwiederholung ohne zusätzliche Personalisierung."
                    ),
                ],
                checkpoint=f"Am Ende von Woche {week}: dokumentieren Sie nur den Abschlusswert des festen Moduls {module_label} und wechseln Sie dann zum nächsten Modul der Sequenz.",
                linked_skills=[module],
            )
        )
    return plan


def generate_roadmap(req: RoadmapGenerateRequest) -> RoadmapPayload:
    current_level = _resolve_current_level(req)
    target_label = GOAL_EXAM_LABELS.get(req.target_exam, req.target_exam)
    recommendation_strategy = current_recommendation_strategy()
    title = _roadmap_title(current_level, req.target_level)
    summary = _roadmap_summary(current_level, req.target_level, req.target_exam)
    must_know = ROADMAP_KNOWLEDGE.get(req.target_level, ROADMAP_KNOWLEDGE["B2"])
    milestones = [
        RoadmapMilestone(title=f"Brückenniveau Richtung {next_level(current_level)}", description="Grundstrukturen stabilisieren, häufige Fehler reduzieren und Lernrhythmus festigen.", target_week=max(2, req.weeks // 3)),
        RoadmapMilestone(title="Sichere Produktion", description="Schreiben und Sprechen werden strukturierter, klarer und weniger fehleranfällig.", target_week=max(3, (req.weeks * 2) // 3)),
        RoadmapMilestone(title=f"Bereit für {target_label}", description="Simulationen werden mit stabilen Ergebnissen oberhalb des Zielbereichs bearbeitet.", target_week=req.weeks),
    ]
    weekly_plan = _roadmap_weeks(current_level, req.target_level, req.weeks, req.target_exam)
    if recommendation_strategy == "fixed_path_v1":
        summary = (
            f"Dieser Lernplan dient als feste Vergleichsbedingung auf dem Weg von {current_level} zu {req.target_level} "
            f"mit Fokus auf {target_label}. Die Reihenfolge bleibt bewusst nicht personalisiert."
        )
        weekly_plan = _fixed_path_weeks(req.target_level, req.weeks, req.target_exam)
    roadmap = RoadmapPayload(
        roadmap_id=make_id("roadmap"),
        title=title,
        current_level=current_level,
        target_level=req.target_level,
        target_exam=req.target_exam,
        summary=summary,
        must_know=must_know,
        weekly_plan=weekly_plan,
        milestones=milestones,
        is_active=False,
        created_at=utc_now_iso(),
    )
    with connection_scope() as conn:
        conn.execute(
            """
            INSERT INTO roadmaps (
                id, current_level, target_level, target_exam, title, summary, must_know_json,
                weekly_plan_json, milestones_json, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                roadmap.roadmap_id,
                roadmap.current_level,
                roadmap.target_level,
                roadmap.target_exam,
                roadmap.title,
                roadmap.summary,
                json.dumps(roadmap.must_know, ensure_ascii=False),
                json.dumps([week.model_dump() for week in roadmap.weekly_plan], ensure_ascii=False),
                json.dumps([milestone.model_dump() for milestone in roadmap.milestones], ensure_ascii=False),
                roadmap.created_at,
                roadmap.created_at,
            ),
        )
    save_recommendation_event(
        source="roadmap_generate",
        goal_exam=req.target_exam,
        recommended_scope="roadmap",
        priority_module=None,
        next_action=roadmap.summary,
        context_payload={
            "roadmap_id": roadmap.roadmap_id,
            "current_level": roadmap.current_level,
            "target_level": roadmap.target_level,
            "weeks": req.weeks,
            "recommendation_strategy": recommendation_strategy,
        },
        strategy_label=recommendation_strategy,
    )
    return roadmap


def get_current_roadmap() -> RoadmapPayload | None:
    with connection_scope() as conn:
        row = conn.execute("SELECT * FROM roadmaps WHERE is_active = 1 ORDER BY updated_at DESC LIMIT 1").fetchone()
        if not row:
            return None

        title, summary, changed = _normalize_legacy_roadmap_copy(row)
        if changed:
            conn.execute(
                "UPDATE roadmaps SET title = ?, summary = ?, updated_at = ? WHERE id = ?",
                (title, summary, utc_now_iso(), row["id"]),
            )
        row_data = dict(row)
        row_data["title"] = title
        row_data["summary"] = summary

    return RoadmapPayload(
        roadmap_id=row_data["id"],
        title=row_data["title"],
        current_level=row_data["current_level"],
        target_level=row_data["target_level"],
        target_exam=row_data["target_exam"],
        summary=row_data["summary"],
        must_know=json.loads(row_data["must_know_json"]),
        weekly_plan=[RoadmapWeek.model_validate(item) for item in json.loads(row_data["weekly_plan_json"])],
        milestones=[RoadmapMilestone.model_validate(item) for item in json.loads(row_data["milestones_json"])],
        is_active=bool(row_data["is_active"]),
        created_at=row_data["created_at"],
    )


def activate_roadmap(req: RoadmapActivateRequest) -> RoadmapPayload:
    now = utc_now_iso()
    with connection_scope() as conn:
        conn.execute("UPDATE roadmaps SET is_active = 0, updated_at = ?", (now,))
        conn.execute("UPDATE roadmaps SET is_active = 1, updated_at = ? WHERE id = ?", (now, req.roadmap_id))
    roadmap = get_current_roadmap()
    if not roadmap:
        raise ValueError("Lernplan nicht gefunden.")
    return roadmap
