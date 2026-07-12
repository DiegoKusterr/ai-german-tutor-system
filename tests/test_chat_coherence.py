import main


def _reset_sessions() -> None:
    with main.SESSIONS_LOCK:
        main.SESSIONS.clear()


def test_resolve_chat_conversation_state_locks_persona_key(monkeypatch) -> None:
    _reset_sessions()
    monkeypatch.setattr(main, "schedule_state_persist", lambda *args, **kwargs: None)

    conversation_id, _ = main.resolve_chat_conversation_state(None, "B2", "coach")
    same_conversation_id, _ = main.resolve_chat_conversation_state(conversation_id, "B2", "examiner")
    snapshot = main.get_session_snapshot(conversation_id)

    assert conversation_id == same_conversation_id
    assert snapshot is not None
    assert snapshot["coherence"]["persona_key"] == "coach"


def test_transcript_response_includes_locked_conversation_persona(monkeypatch) -> None:
    _reset_sessions()
    monkeypatch.setattr(main, "schedule_state_persist", lambda *args, **kwargs: None)

    conversation_id, _ = main.resolve_chat_conversation_state(None, "B2", "examiner")
    response = main.transcript(conversation_id)

    assert response.persona_key == "examiner"


def test_build_chat_coherence_system_note_uses_latest_active_facts() -> None:
    transcript = [
        {"role": "user", "text": "Ich heiße Diego.", "timestamp": "t1"},
        {"role": "assistant", "text": "Hallo Diego.", "timestamp": "t2"},
        {"role": "user", "text": "Ich wohne in Berlin.", "timestamp": "t3"},
        {"role": "user", "text": "Ich wohne in Madrid.", "timestamp": "t4"},
    ]

    coherence = main.build_transcript_coherence(transcript, persona_key="examiner")
    note = main.build_chat_coherence_system_note(coherence)

    assert note is not None
    assert "Persona bleibt: Examiner." in note
    assert "Nutzername: Diego" in note
    assert "Wohnort: Madrid" in note
    assert "Wohnort: Berlin" not in note
    assert "neueste aktive Aussage" in note


def test_generate_chat_reply_uses_persona_assistant_facts_for_self_identity() -> None:
    transcript = [{"role": "user", "text": "Wer bist du?", "timestamp": "t1"}]
    coherence = main.build_transcript_coherence(transcript, persona_key="coach")

    reply, provider_used, degraded_reason = main.generate_chat_reply(
        message="Wer bist du?",
        level="B2",
        transcript=transcript,
        preferred_provider="rulebased",
        coherence=coherence,
    )

    normalized_reply = main.normalize_for_matching(reply)

    assert provider_used == "rulebased"
    assert degraded_reason == "fast_path"
    assert "deutsch-coach" in normalized_reply


def test_edit_and_restore_rebuild_coherence_from_active_branch_only(monkeypatch) -> None:
    _reset_sessions()
    monkeypatch.setattr(main, "schedule_state_persist", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "generate_regenerated_chat_reply", lambda **kwargs: "Verstanden.")

    conversation_id = "coherence-edit-case"
    main.ensure_session(conversation_id, "B2", requested_persona_key="studio")

    first_user = main.append_transcript(
        conversation_id,
        "B2",
        "user",
        "Ich wohne in Berlin.",
        meta_source="blocking",
    )
    assert first_user is not None
    main.append_transcript(
        conversation_id,
        "B2",
        "assistant",
        "Alles klar.",
        reply_to_id=str(first_user.get("id") or ""),
        version_group_id=str(first_user.get("version_group_id") or ""),
        version_index=int(first_user.get("version_index") or 1),
        meta_source="blocking",
    )

    later_user = main.append_transcript(
        conversation_id,
        "B2",
        "user",
        "Ich arbeite als Lehrer.",
        meta_source="blocking",
    )
    assert later_user is not None
    main.append_transcript(
        conversation_id,
        "B2",
        "assistant",
        "Gut zu wissen.",
        reply_to_id=str(later_user.get("id") or ""),
        version_group_id=str(later_user.get("version_group_id") or ""),
        version_index=int(later_user.get("version_index") or 1),
        meta_source="blocking",
    )
    main.rebuild_session_coherence(conversation_id)

    edited = main.mutate_user_message_version(
        conversation_id=conversation_id,
        entry_id=str(first_user.get("id") or ""),
        replacement_text="Ich wohne in Madrid.",
        source="edited",
    )
    edited_snapshot = main.get_session_snapshot(conversation_id)

    assert edited_snapshot is not None
    assert edited_snapshot["coherence"]["conversation_facts"]["user_city"] == "Madrid"
    assert "user_job" not in edited_snapshot["coherence"]["conversation_facts"]
    assert all(entry.role in {"user", "assistant"} for entry in edited.transcript)

    restored = main.mutate_user_message_version(
        conversation_id=conversation_id,
        entry_id=edited.entry_id,
        replacement_text="",
        source="restored",
        restore_from_entry_id=str(first_user.get("id") or ""),
    )
    restored_snapshot = main.get_session_snapshot(conversation_id)

    assert restored_snapshot is not None
    assert restored_snapshot["coherence"]["conversation_facts"]["user_city"] == "Berlin"
    assert "user_job" not in restored_snapshot["coherence"]["conversation_facts"]
    assert restored.transcript[-1].role == "assistant"
