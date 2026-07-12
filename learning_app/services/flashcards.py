from __future__ import annotations

import json
from datetime import date
from typing import Any

from ..db import connection_scope
from ..learning_materials import STARTER_DECKS
from ..schemas import (
    CardCreateRequest,
    CardPayload,
    CardUpdateRequest,
    DeckCreateRequest,
    DeckDetailPayload,
    DeckPayload,
    DeckUpdateRequest,
    FlashcardImportPayload,
    FlashcardImportRequest,
    ReviewGradePayload,
    ReviewGradeRequest,
    ReviewNextPayload,
    ReviewNextRequest,
    StarterDeckImportPayload,
    StarterDeckSummary,
)
from ..sm2 import SM2State, review_fixed_intervals, review_sm2
from .common import current_review_strategy, make_id, resolve_recommendation_attribution, today_iso, to_json, utc_now_iso


def _deck_counts(conn: Any, deck_id: str) -> tuple[int, int]:
    total_cards = conn.execute("SELECT COUNT(*) FROM cards WHERE deck_id = ?", (deck_id,)).fetchone()[0]
    due_cards = conn.execute(
        "SELECT COUNT(*) FROM cards WHERE deck_id = ? AND due_date <= ?",
        (deck_id, today_iso()),
    ).fetchone()[0]
    return int(total_cards), int(due_cards)


def _deck_payload_from_row(conn: Any, row: Any) -> DeckPayload:
    total_cards, due_cards = _deck_counts(conn, row["id"])
    return DeckPayload(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        source=row["source"],
        tags=json.loads(row["tags_json"]),
        total_cards=total_cards,
        due_cards=due_cards,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _card_payload_from_row(row: Any) -> CardPayload:
    return CardPayload(
        id=row["id"],
        deck_id=row["deck_id"],
        card_type=row["card_type"],
        front=row["front"],
        back=row["back"],
        extra=json.loads(row["extra_json"]),
        tags=json.loads(row["tags_json"]),
        due_date=row["due_date"],
        easiness=float(row["easiness"]),
        interval_days=int(row["interval_days"]),
        repetitions=int(row["repetitions"]),
    )


def create_deck(req: DeckCreateRequest) -> DeckPayload:
    deck_id = make_id("deck")
    now = utc_now_iso()
    with connection_scope() as conn:
        conn.execute(
            """
            INSERT INTO decks (id, name, description, source, tags_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (deck_id, req.name, req.description, req.source, to_json(req.tags), now, now),
        )
        row = conn.execute("SELECT * FROM decks WHERE id = ?", (deck_id,)).fetchone()
        return _deck_payload_from_row(conn, row)


def list_decks() -> list[DeckPayload]:
    with connection_scope() as conn:
        rows = conn.execute("SELECT * FROM decks ORDER BY updated_at DESC").fetchall()
        return [_deck_payload_from_row(conn, row) for row in rows]


def get_deck_detail(deck_id: str) -> DeckDetailPayload:
    with connection_scope() as conn:
        row = conn.execute("SELECT * FROM decks WHERE id = ?", (deck_id,)).fetchone()
        if not row:
            raise ValueError("Kartensatz nicht gefunden.")
        cards = conn.execute(
            "SELECT * FROM cards WHERE deck_id = ? ORDER BY due_date ASC, created_at ASC",
            (deck_id,),
        ).fetchall()
        deck = _deck_payload_from_row(conn, row)
        return DeckDetailPayload(**deck.model_dump(), cards=[_card_payload_from_row(card) for card in cards])


def update_deck(deck_id: str, req: DeckUpdateRequest) -> DeckPayload:
    with connection_scope() as conn:
        conn.execute(
            "UPDATE decks SET name = ?, description = ?, tags_json = ?, updated_at = ? WHERE id = ?",
            (req.name, req.description, to_json(req.tags), utc_now_iso(), deck_id),
        )
        row = conn.execute("SELECT * FROM decks WHERE id = ?", (deck_id,)).fetchone()
        if not row:
            raise ValueError("Kartensatz nicht gefunden.")
        return _deck_payload_from_row(conn, row)


def delete_deck(deck_id: str) -> None:
    with connection_scope() as conn:
        conn.execute("DELETE FROM decks WHERE id = ?", (deck_id,))


def create_card(req: CardCreateRequest) -> CardPayload:
    card_id = make_id("card")
    now = utc_now_iso()
    with connection_scope() as conn:
        deck_row = conn.execute("SELECT id FROM decks WHERE id = ?", (req.deck_id,)).fetchone()
        if not deck_row:
            raise ValueError("Kartensatz nicht gefunden.")
        conn.execute(
            """
            INSERT INTO cards (
                id, deck_id, card_type, front, back, extra_json, tags_json, due_date, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (card_id, req.deck_id, req.card_type, req.front, req.back, to_json(req.extra), to_json(req.tags), today_iso(), now, now),
        )
        conn.execute("UPDATE decks SET updated_at = ? WHERE id = ?", (now, req.deck_id))
        row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        return _card_payload_from_row(row)


def update_card(card_id: str, req: CardUpdateRequest) -> CardPayload:
    with connection_scope() as conn:
        card_row = conn.execute("SELECT deck_id FROM cards WHERE id = ?", (card_id,)).fetchone()
        if not card_row:
            raise ValueError("Karte nicht gefunden.")
        conn.execute(
            """
            UPDATE cards
            SET card_type = ?, front = ?, back = ?, extra_json = ?, tags_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (req.card_type, req.front, req.back, to_json(req.extra), to_json(req.tags), utc_now_iso(), card_id),
        )
        conn.execute("UPDATE decks SET updated_at = ? WHERE id = ?", (utc_now_iso(), card_row["deck_id"]))
        row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        return _card_payload_from_row(row)


def delete_card(card_id: str) -> None:
    with connection_scope() as conn:
        row = conn.execute("SELECT deck_id FROM cards WHERE id = ?", (card_id,)).fetchone()
        conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))
        if row:
            conn.execute("UPDATE decks SET updated_at = ? WHERE id = ?", (utc_now_iso(), row["deck_id"]))


def import_flashcards(req: FlashcardImportRequest) -> FlashcardImportPayload:
    deck = create_deck(
        DeckCreateRequest(
            name=req.deck_name,
            description=req.deck_description,
            source=req.source,
            tags=req.tags,
        )
    )
    imported_cards = 0

    items = list(req.items)
    if req.raw_text:
        for line in req.raw_text.splitlines():
            cleaned = line.strip()
            if not cleaned:
                continue
            if ";" in cleaned:
                front, back = [part.strip() for part in cleaned.split(";", 1)]
            else:
                front, back = cleaned, cleaned
            items.append(
                {
                    "lemma": front,
                    "translation": back,
                    "example": "",
                    "collocation": "",
                    "notes": "",
                    "topic": req.deck_name,
                    "id": make_id("vocab"),
                }
            )

    for item in items:
        if hasattr(item, "lemma"):
            front = item.lemma
            back = item.translation
            extra = {
                "example": item.example,
                "collocation": item.collocation,
                "notes": item.notes,
                "gender": getattr(item, "gender", None),
                "plural": getattr(item, "plural", None),
            }
            tags = [req.source, getattr(item, "topic", req.deck_name)]
        else:
            front = str(item["lemma"])
            back = str(item["translation"])
            extra = {
                "example": item.get("example", ""),
                "collocation": item.get("collocation", ""),
                "notes": item.get("notes", ""),
            }
            tags = [req.source, str(item.get("topic", req.deck_name))]
        create_card(
            CardCreateRequest(
                deck_id=deck.id,
                card_type="multi_field",
                front=front,
                back=back,
                extra=extra,
                tags=tags,
            )
        )
        imported_cards += 1

    return FlashcardImportPayload(deck=get_deck_detail(deck.id), imported_cards=imported_cards)


def list_starter_decks() -> list[StarterDeckSummary]:
    summaries: list[StarterDeckSummary] = []
    for key, deck in STARTER_DECKS.items():
        summaries.append(
            StarterDeckSummary(
                key=key,
                name=deck["name"],
                description=deck["description"],
                level=deck["level"],
                tags=list(deck["tags"]),
                card_count=len(deck["cards"]),
                sample_fronts=[card["front"] for card in deck["cards"][:6]],
            )
        )
    return summaries


def import_starter_deck(deck_key: str) -> StarterDeckImportPayload:
    deck = STARTER_DECKS.get(deck_key)
    if not deck:
        raise ValueError("Startset nicht gefunden.")
    created_deck = create_deck(
        DeckCreateRequest(
            name=deck["name"],
            description=deck["description"],
            source=f"starter:{deck_key}",
            tags=list(deck["tags"]),
        )
    )
    imported_cards = 0
    for card in deck["cards"]:
        create_card(
            CardCreateRequest(
                deck_id=created_deck.id,
                card_type="multi_field",
                front=card["front"],
                back=card["back"],
                extra=dict(card.get("extra", {})),
                tags=list(deck["tags"]),
            )
        )
        imported_cards += 1
    imported = FlashcardImportPayload(deck=get_deck_detail(created_deck.id), imported_cards=imported_cards)
    with connection_scope() as conn:
        conn.execute(
            "INSERT INTO starter_deck_imports (id, starter_key, deck_id, imported_at) VALUES (?, ?, ?, ?)",
            (make_id("starterimport"), deck_key, imported.deck.id, utc_now_iso()),
        )
    return StarterDeckImportPayload(
            starter_deck=StarterDeckSummary(
                key=deck_key,
                name=deck["name"],
                description=deck["description"],
                level=deck["level"],
                tags=list(deck["tags"]),
                card_count=len(deck["cards"]),
                sample_fronts=[card["front"] for card in deck["cards"][:6]],
            ),
            imported=imported,
        )


def next_review_card(req: ReviewNextRequest) -> ReviewNextPayload:
    with connection_scope() as conn:
        if req.deck_id:
            row = conn.execute(
                """
                SELECT * FROM cards
                WHERE deck_id = ? AND due_date <= ?
                ORDER BY due_date ASC, repetitions ASC, created_at ASC
                LIMIT 1
                """,
                (req.deck_id, today_iso()),
            ).fetchone()
            due_count = conn.execute(
                "SELECT COUNT(*) FROM cards WHERE deck_id = ? AND due_date <= ?",
                (req.deck_id, today_iso()),
            ).fetchone()[0]
        else:
            row = conn.execute(
                """
                SELECT * FROM cards
                WHERE due_date <= ?
                ORDER BY due_date ASC, repetitions ASC, created_at ASC
                LIMIT 1
                """,
                (today_iso(),),
            ).fetchone()
            due_count = conn.execute("SELECT COUNT(*) FROM cards WHERE due_date <= ?", (today_iso(),)).fetchone()[0]

        recommendation_event_id = req.recommendation_event_id
        if not row:
            return ReviewNextPayload(
                card=None,
                due_count=int(due_count),
                message="Im Moment sind keine Karten fällig.",
                recommendation_event_id=recommendation_event_id,
            )
        return ReviewNextPayload(
            card=_card_payload_from_row(row),
            due_count=int(due_count),
            message="Karte für die nächste Wiederholung bereit.",
            recommendation_event_id=recommendation_event_id,
        )


def _calendar_day(raw_value: Any) -> date | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _apply_review_strategy(review_strategy: str, state: SM2State, quality: int, review_day: date) -> SM2State:
    if review_strategy == "fixed_interval_v1":
        return review_fixed_intervals(state, quality, review_day=review_day)
    return review_sm2(state, quality, review_day=review_day)


def grade_review(req: ReviewGradeRequest) -> ReviewGradePayload:
    with connection_scope() as conn:
        row = conn.execute("SELECT * FROM cards WHERE id = ?", (req.card_id,)).fetchone()
        if not row:
            raise ValueError("Karte nicht gefunden.")
        review_strategy = current_review_strategy()
        launched_from_recommendation, recommendation_event_id, linked_recommendation_strategy = resolve_recommendation_attribution(
            conn,
            req.recommendation_event_id,
        )
        review_day = date.today()
        state = SM2State(
            easiness=float(row["easiness"]),
            interval_days=int(row["interval_days"]),
            repetitions=int(row["repetitions"]),
            due_date=date.fromisoformat(row["due_date"]),
        )
        previous_due_date = date.fromisoformat(row["due_date"])
        previous_review_day = _calendar_day(row["last_reviewed_at"]) or _calendar_day(row["created_at"]) or review_day
        days_since_last_review = max(0, (review_day - previous_review_day).days)
        days_overdue = max(0, (review_day - previous_due_date).days)
        successful_recall = 1 if int(req.quality) >= 3 else 0
        updated = _apply_review_strategy(review_strategy, state, req.quality, review_day)
        now = utc_now_iso()
        conn.execute(
            """
            UPDATE cards
            SET easiness = ?, interval_days = ?, repetitions = ?, due_date = ?, last_reviewed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                updated.easiness,
                updated.interval_days,
                updated.repetitions,
                updated.due_date.isoformat(),
                now,
                now,
                req.card_id,
            ),
        )
        conn.execute(
            """
            INSERT INTO reviews (
                id, card_id, quality, easiness, interval_days, repetitions, due_date, review_strategy,
                previous_easiness, previous_interval_days, previous_repetitions, previous_due_date,
                days_since_last_review, days_overdue, successful_recall,
                launched_from_recommendation, recommendation_event_id, linked_recommendation_strategy, reviewed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                make_id("review"),
                req.card_id,
                req.quality,
                updated.easiness,
                updated.interval_days,
                updated.repetitions,
                updated.due_date.isoformat(),
                review_strategy,
                state.easiness,
                state.interval_days,
                state.repetitions,
                previous_due_date.isoformat(),
                days_since_last_review,
                days_overdue,
                successful_recall,
                launched_from_recommendation,
                recommendation_event_id,
                linked_recommendation_strategy,
                now,
            ),
        )
        due_remaining = conn.execute("SELECT COUNT(*) FROM cards WHERE due_date <= ?", (today_iso(),)).fetchone()[0]
        return ReviewGradePayload(
            card_id=req.card_id,
            quality=req.quality,
            next_due_date=updated.due_date.isoformat(),
            easiness=updated.easiness,
            interval_days=updated.interval_days,
            repetitions=updated.repetitions,
            due_count_remaining=int(due_remaining),
            review_strategy=review_strategy,
            successful_recall=bool(successful_recall),
            days_since_last_review=days_since_last_review,
            days_overdue=days_overdue,
        )
