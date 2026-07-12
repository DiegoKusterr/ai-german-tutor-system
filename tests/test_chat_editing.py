import main
from fastapi.testclient import TestClient


def reset_chat_state() -> None:
    with main.SESSIONS_LOCK:
        main.SESSIONS.clear()


def seed_conversation(conversation_id: str = "conv-edit") -> dict[str, str]:
    main.ensure_session(conversation_id, "B2")
    user_1 = main.append_transcript(conversation_id, "B2", "user", "Ich heiße Maria.", meta_source="blocking")
    assistant_1 = main.append_transcript(
        conversation_id,
        "B2",
        "assistant",
        "Freut mich, Maria.",
        reply_to_id=str(user_1["id"]),
        version_group_id=str(user_1["version_group_id"]),
        version_index=int(user_1["version_index"]),
        meta_source="blocking",
    )
    user_2 = main.append_transcript(conversation_id, "B2", "user", "Wo wohnst du?", meta_source="blocking")
    assistant_2 = main.append_transcript(
        conversation_id,
        "B2",
        "assistant",
        "Ich lebe nicht an einem festen Ort, weil ich digital bin.",
        reply_to_id=str(user_2["id"]),
        version_group_id=str(user_2["version_group_id"]),
        version_index=int(user_2["version_index"]),
        meta_source="blocking",
    )
    user_3 = main.append_transcript(conversation_id, "B2", "user", "Was machst du am Wochenende?", meta_source="blocking")
    assistant_3 = main.append_transcript(
        conversation_id,
        "B2",
        "assistant",
        "Ich spreche hier mit dir auf Deutsch.",
        reply_to_id=str(user_3["id"]),
        version_group_id=str(user_3["version_group_id"]),
        version_index=int(user_3["version_index"]),
        meta_source="blocking",
    )
    return {
        "conversation_id": conversation_id,
        "user_1": str(user_1["id"]),
        "assistant_1": str(assistant_1["id"]),
        "user_2": str(user_2["id"]),
        "assistant_2": str(assistant_2["id"]),
        "user_3": str(user_3["id"]),
        "assistant_3": str(assistant_3["id"]),
    }


def test_parse_session_state_lazily_upgrades_legacy_transcript_entries() -> None:
    parsed = main._parse_session_state(
        {
            "level": "B2",
            "started_at": "2026-03-30T08:00:00+00:00",
            "transcript": [
                {"role": "user", "text": "Hallo", "timestamp": "2026-03-30T08:01:00+00:00"},
                {"role": "assistant", "text": "Hallo!", "timestamp": "2026-03-30T08:01:03+00:00"},
            ],
        }
    )

    assert parsed is not None
    assert parsed["next_version_group_index"] >= 2
    assert len(parsed["transcript"]) == 2
    user_entry, assistant_entry = parsed["transcript"]
    assert user_entry["status"] == "active"
    assert user_entry["version_index"] == 1
    assert user_entry["version_group_id"].startswith("vg-")
    assert assistant_entry["reply_to_id"] == user_entry["id"]
    assert assistant_entry["status"] == "active"
    assert assistant_entry["version_group_id"] == user_entry["version_group_id"]


def test_blocking_chat_and_stream_commit_store_transcript_metadata(monkeypatch) -> None:
    reset_chat_state()
    client = TestClient(main.app)
    monkeypatch.setattr(main, "schedule_state_persist", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "resolve_provider", lambda: "rulebased")
    monkeypatch.setattr(main, "should_block_rulebased_mode", lambda: False)

    response = client.post("/chat", json={"message": "Wie alt bist du?", "level": "B2"})
    assert response.status_code == 200
    conversation_id = response.json()["conversation_id"]

    session = main.get_session_snapshot(conversation_id)
    assert session is not None
    active_transcript = main.get_active_transcript(session)
    assert len(active_transcript) == 2
    assert active_transcript[0]["status"] == "active"
    assert active_transcript[0]["version_index"] == 1
    assert active_transcript[1]["reply_to_id"] == active_transcript[0]["id"]
    assert active_transcript[1]["version_group_id"] == active_transcript[0]["version_group_id"]

    conversation_id = "stream-commit-metadata"
    main.ensure_session(conversation_id, "B2")
    commit_response = client.post(
        "/api/tutor/chat/commit",
        json={
            "conversation_id": conversation_id,
            "level": "B2",
            "message": "Wie heißt du?",
            "reply": "Ich bin dein deutscher Gesprächspartner zum Üben.",
        },
    )
    assert commit_response.status_code == 200
    stream_session = main.get_session_snapshot(conversation_id)
    assert stream_session is not None
    stream_active = main.get_active_transcript(stream_session)
    assert len(stream_active) == 2
    assert stream_active[0]["meta"]["source"] == "streamed"
    assert stream_active[1]["reply_to_id"] == stream_active[0]["id"]


def test_edit_active_user_message_supersedes_and_outdates_downstream(monkeypatch) -> None:
    reset_chat_state()
    conversation = seed_conversation()
    client = TestClient(main.app)
    monkeypatch.setattr(main, "schedule_state_persist", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "resolve_provider", lambda: "rulebased")
    monkeypatch.setattr(main, "should_block_rulebased_mode", lambda: False)

    response = client.post(
        "/api/chat/message/edit",
        json={
            "conversation_id": conversation["conversation_id"],
            "entry_id": conversation["user_2"],
            "text": "Wie alt bist du? Antworte in 1 Satz.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    session = main.get_session_snapshot(conversation["conversation_id"])
    assert session is not None

    full_transcript = session["transcript"]
    active_transcript = main.get_active_transcript(session)
    active_texts = [item["text"] for item in active_transcript]
    assert active_texts == [
        "Ich heiße Maria.",
        "Freut mich, Maria.",
        "Wie alt bist du? Antworte in 1 Satz.",
        active_transcript[-1]["text"],
    ]
    assert conversation["user_3"] not in {item["id"] for item in active_transcript}
    assert conversation["assistant_3"] not in {item["id"] for item in active_transcript}

    original_user_2 = next(item for item in full_transcript if item["id"] == conversation["user_2"])
    original_assistant_2 = next(item for item in full_transcript if item["id"] == conversation["assistant_2"])
    original_user_3 = next(item for item in full_transcript if item["id"] == conversation["user_3"])
    original_assistant_3 = next(item for item in full_transcript if item["id"] == conversation["assistant_3"])
    new_user_entry = next(item for item in full_transcript if item["id"] == payload["entry_id"])
    new_assistant_entry = next(item for item in full_transcript if item["id"] == payload["assistant_entry_id"])

    assert original_user_2["status"] == "superseded"
    assert original_assistant_2["status"] == "outdated"
    assert original_user_3["status"] == "outdated"
    assert original_assistant_3["status"] == "outdated"
    assert new_user_entry["status"] == "active"
    assert new_user_entry["version_group_id"] == original_user_2["version_group_id"]
    assert new_user_entry["version_index"] == 2
    assert new_user_entry["edited_from_id"] == original_user_2["id"]
    assert new_user_entry["meta"]["source"] == "edited"
    assert new_assistant_entry["status"] == "active"
    assert new_assistant_entry["reply_to_id"] == new_user_entry["id"]
    assert new_assistant_entry["meta"]["source"] == "regenerated"
    assert set(payload["invalidated_entry_ids"]) >= {
        conversation["user_2"],
        conversation["assistant_2"],
        conversation["user_3"],
        conversation["assistant_3"],
    }


def test_versions_restore_history_and_active_only_consumers(monkeypatch) -> None:
    reset_chat_state()
    conversation = seed_conversation("conv-restore")
    client = TestClient(main.app)
    monkeypatch.setattr(main, "schedule_state_persist", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "resolve_provider", lambda: "rulebased")
    monkeypatch.setattr(main, "should_block_rulebased_mode", lambda: False)

    edit_response = client.post(
        "/api/chat/message/edit",
        json={
            "conversation_id": conversation["conversation_id"],
            "entry_id": conversation["user_2"],
            "text": "Wie alt bist du? Antworte in 1 Satz.",
        },
    )
    assert edit_response.status_code == 200
    edited_entry_id = edit_response.json()["entry_id"]

    versions_before_restore = client.get(
        f"/api/chat/transcript/{conversation['conversation_id']}/message/{edited_entry_id}/versions"
    )
    assert versions_before_restore.status_code == 200
    versions_payload = versions_before_restore.json()
    assert len(versions_payload["versions"]) == 2
    assert versions_payload["active_entry_id"] == edited_entry_id

    restore_response = client.post(
        "/api/chat/message/restore",
        json={
            "conversation_id": conversation["conversation_id"],
            "entry_id": edited_entry_id,
            "restore_from_entry_id": conversation["user_2"],
        },
    )
    assert restore_response.status_code == 200
    restore_payload = restore_response.json()

    transcript_response = client.get(f"/api/chat/transcript/{conversation['conversation_id']}")
    assert transcript_response.status_code == 200
    transcript_payload = transcript_response.json()
    transcript_texts = [item["text"] for item in transcript_payload["transcript"]]
    assert transcript_texts == [
        "Ich heiße Maria.",
        "Freut mich, Maria.",
        "Wo wohnst du?",
        transcript_payload["transcript"][-1]["text"],
    ]
    assert all(item["status"] == "active" for item in transcript_payload["transcript"])

    history_response = client.get("/api/chat/history")
    assert history_response.status_code == 200
    summary = next(item for item in history_response.json() if item["conversation_id"] == conversation["conversation_id"])
    assert summary["turns"] == 2
    assert summary["preview"] == "Wo wohnst du?"

    finish_response = client.post("/api/chat/finish", json={"conversation_id": conversation["conversation_id"]})
    assert finish_response.status_code == 200
    finish_payload = finish_response.json()
    assert [item["text"] for item in finish_payload["transcript"]] == transcript_texts
    assert all(item["status"] == "active" for item in finish_payload["transcript"])

    session = main.get_session_snapshot(conversation["conversation_id"])
    assert session is not None
    versions_after_restore = client.get(
        f"/api/chat/transcript/{conversation['conversation_id']}/message/{restore_payload['entry_id']}/versions"
    )
    assert versions_after_restore.status_code == 200
    after_restore_payload = versions_after_restore.json()
    assert len(after_restore_payload["versions"]) == 3
    assert after_restore_payload["active_entry_id"] == restore_payload["entry_id"]

    working_prompt = main.transcript_to_prompt(
        main.build_working_chat_transcript(session, message="Noch eine Frage?")
    )
    assert "Was machst du am Wochenende?" not in working_prompt
    assert "Wie alt bist du? Antworte in 1 Satz." not in working_prompt
