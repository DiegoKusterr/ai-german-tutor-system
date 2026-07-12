from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..db import connection_scope
from ..schemas import MockGenerationAggregate, MockGenerationHealthPayload, MockGenerationRunPayload
from .common import from_json, level_rank, make_id, to_json, utc_now_iso

MODULE_ORDER = {
    "lesen": 0,
    "hoeren": 1,
    "schreiben": 2,
    "sprechen": 3,
    "full": 4,
}


def _row_to_mock_run(row: Any) -> MockGenerationRunPayload:
    return MockGenerationRunPayload(
        run_id=row["id"],
        created_at=row["created_at"],
        level=row["level"],
        module=row["module"],
        scope=row["scope"],
        variant_seed=row["variant_seed"],
        generation_mode=row["generation_mode"],
        fallback_used=bool(row["fallback_used"]),
        llm_model=row["llm_model"],
        elapsed_ms=int(row["elapsed_ms"]),
        item_count=int(row["item_count"]),
        media_pack_count=int(row["media_pack_count"]),
        validation_notes=list(from_json(row["validation_notes_json"]) or []),
        module_brief_used=bool(row["module_brief_used"]),
    )


def save_mock_generation_run(
    *,
    level: str,
    module: str,
    scope: str,
    variant_seed: str | None,
    generation_mode: str,
    fallback_used: bool,
    llm_model: str | None,
    elapsed_ms: int,
    item_count: int,
    media_pack_count: int,
    validation_notes: list[str] | None = None,
    module_brief_used: bool = False,
) -> MockGenerationRunPayload:
    payload = MockGenerationRunPayload(
        run_id=make_id("mockrun"),
        created_at=utc_now_iso(),
        level=level,
        module=module,
        scope=scope,
        variant_seed=variant_seed,
        generation_mode=generation_mode,
        fallback_used=fallback_used,
        llm_model=llm_model,
        elapsed_ms=max(0, int(elapsed_ms)),
        item_count=max(0, int(item_count)),
        media_pack_count=max(0, int(media_pack_count)),
        validation_notes=[str(item) for item in (validation_notes or [])[:8]],
        module_brief_used=module_brief_used,
    )
    with connection_scope() as conn:
        conn.execute(
            """
            INSERT INTO mock_generation_runs (
                id, level, module, scope, variant_seed, generation_mode, fallback_used, llm_model,
                elapsed_ms, item_count, media_pack_count, validation_notes_json, module_brief_used, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.run_id,
                payload.level,
                payload.module,
                payload.scope,
                payload.variant_seed,
                payload.generation_mode,
                1 if payload.fallback_used else 0,
                payload.llm_model,
                payload.elapsed_ms,
                payload.item_count,
                payload.media_pack_count,
                to_json(payload.validation_notes),
                1 if payload.module_brief_used else 0,
                payload.created_at,
            ),
        )
    return payload


def list_mock_generation_runs(limit: int = 10) -> list[MockGenerationRunPayload]:
    with connection_scope() as conn:
        rows = conn.execute(
            """
            SELECT id, level, module, scope, variant_seed, generation_mode, fallback_used, llm_model,
                   elapsed_ms, item_count, media_pack_count, validation_notes_json, module_brief_used, created_at
            FROM mock_generation_runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
    return [_row_to_mock_run(row) for row in rows]


def get_mock_generation_health(recent_limit: int = 6, window_limit: int = 60) -> MockGenerationHealthPayload:
    recent_runs = list_mock_generation_runs(limit=recent_limit)
    with connection_scope() as conn:
        rows = conn.execute(
            """
            SELECT id, level, module, scope, variant_seed, generation_mode, fallback_used, llm_model,
                   elapsed_ms, item_count, media_pack_count, validation_notes_json, module_brief_used, created_at
            FROM mock_generation_runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, int(window_limit)),),
        ).fetchall()
    window_runs = [_row_to_mock_run(row) for row in rows]
    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "elapsed_total": 0, "fallback_total": 0, "modes": defaultdict(int)}
    )
    for run in window_runs:
        bucket = grouped[(run.level, run.module)]
        bucket["count"] += 1
        bucket["elapsed_total"] += run.elapsed_ms
        bucket["fallback_total"] += 1 if run.fallback_used else 0
        bucket["modes"][run.generation_mode] += 1

    aggregates = [
        MockGenerationAggregate(
            level=level,
            module=module,
            total_runs=data["count"],
            fallback_ratio=(data["fallback_total"] / data["count"]) if data["count"] else 0.0,
            average_elapsed_ms=round(data["elapsed_total"] / data["count"]) if data["count"] else 0,
            generation_modes=dict(sorted(data["modes"].items())),
        )
        for (level, module), data in grouped.items()
    ]
    aggregates.sort(key=lambda item: (level_rank(item.level), MODULE_ORDER.get(item.module, 99), item.module))
    return MockGenerationHealthPayload(
        recent_runs=recent_runs,
        aggregates=aggregates,
        window_runs=len(window_runs),
    )
