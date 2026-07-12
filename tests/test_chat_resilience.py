import json
import time
from pathlib import Path

import main
from fastapi.testclient import TestClient


def test_auto_provider_prefers_ollama_when_both_are_available(monkeypatch) -> None:
    monkeypatch.setenv("CHAT_PROVIDER", "auto")
    monkeypatch.setattr(main, "ollama_available", lambda: True)

    assert main.resolve_provider() == "ollama"


def test_transcribe_provider_prefers_local_by_default(monkeypatch) -> None:
    monkeypatch.delenv("TRANSCRIBE_PROVIDER", raising=False)
    monkeypatch.setattr(main, "local_transcribe_available", lambda: True)

    assert main.resolve_transcribe_provider() == "local"


def test_transcribe_provider_returns_none_without_local_backend(monkeypatch) -> None:
    monkeypatch.setenv("TRANSCRIBE_PROVIDER", "local")
    monkeypatch.setattr(main, "local_transcribe_available", lambda: False)

    assert main.resolve_transcribe_provider() == "none"


def test_trim_transcript_respects_char_budget_and_keeps_user_context() -> None:
    transcript = [
        {"role": "user", "text": "Ich spreche heute ueber meinen Arbeitstag.", "timestamp": "t1"},
        {"role": "assistant", "text": "Erzaehl mir mehr ueber deinen Morgen.", "timestamp": "t2"},
        {"role": "user", "text": "Am Morgen hatte ich ein Meeting und danach viel Arbeit.", "timestamp": "t3"},
        {"role": "assistant", "text": "Und wie war die Stimmung im Team?", "timestamp": "t4"},
        {"role": "user", "text": "Sie war gut, aber wir waren alle ziemlich muede.", "timestamp": "t5"},
    ]

    trimmed = main.trim_transcript_for_model(transcript, max_messages=5, max_chars=90)

    assert trimmed
    assert trimmed[0]["role"] == "user"
    assert sum(len(item["text"]) for item in trimmed) <= 90


def test_generate_chat_reply_falls_back_when_primary_output_is_low_quality(monkeypatch) -> None:
    transcript = [{"role": "user", "text": "Was machst du am Wochenende?", "timestamp": "t1"}]

    monkeypatch.setattr(main, "ollama_available", lambda: True)
    monkeypatch.setattr(main, "OLLAMA_WARMED", True)
    monkeypatch.setattr(main, "chat_with_ollama", lambda **_: "As an AI language model, I cannot do that.")

    reply, provider_used, degraded_reason = main.generate_chat_reply(
        message="Was machst du am Wochenende?",
        level="B1",
        transcript=transcript,
        preferred_provider="ollama",
    )

    assert provider_used == "rulebased"
    assert "language model" not in reply.lower()
    assert degraded_reason is not None


def test_extract_chat_reply_constraints_supports_sentence_count_concise_and_simple_german() -> None:
    constraints = main.extract_chat_reply_constraints(
        "Bitte antworte in 3 kurzen Sätzen und benutze einfaches Deutsch."
    )

    assert constraints.sentence_count == 3
    assert constraints.concise is True
    assert constraints.simple_german is True


def test_finalize_assistant_reply_respects_constraints_and_strips_leading_filler() -> None:
    constraints = main.ChatReplyConstraints(sentence_count=3, concise=True)

    reply = main.finalize_assistant_reply(
        "Das ist ein guter Punkt. Hier ist die erste klare Antwort. Dann kommt ein zweiter kurzer Satz. Und hier noch ein dritter.",
        constraints=constraints,
    )

    sentences = main.split_complete_assistant_sentences(reply, constraints=constraints)

    assert len(sentences) == 3
    assert not reply.lower().startswith("das ist ein guter punkt")
    assert len(reply.split()) <= 36


def test_finalize_assistant_reply_can_split_clauses_for_requested_sentence_count() -> None:
    constraints = main.ChatReplyConstraints(sentence_count=3, concise=True, simple_german=True)

    reply = main.finalize_assistant_reply(
        "Ich bin digital, ich habe kein echtes Alter, und ich wohne an keinem festen Ort.",
        constraints=constraints,
    )

    sentences = main.split_complete_assistant_sentences(reply, constraints=constraints)

    assert len(sentences) == 3
    assert sentences[0].startswith("Ich bin digital")
    assert "echtes Alter" in sentences[1]


def test_build_ollama_messages_includes_turn_specific_constraint_note() -> None:
    message = "Answer in 2 sentences and use simple German: Where do you live? How old are you?"
    constraints = main.extract_chat_reply_constraints(message)

    messages = main.build_ollama_messages(
        level="B2",
        transcript=[{"role": "user", "text": message, "timestamp": "t1"}],
        include_memory=False,
        constraints=constraints,
    )

    system_notes = [item["content"] for item in messages if item["role"] == "system"]

    assert any("genau 2 kurze Saetze" in note for note in system_notes)
    assert any("Formulierungen wie 'in 2 Saetzen'" in note for note in system_notes)
    assert any("derselben Reihenfolge" in note for note in system_notes)
    assert any("direkte Antwort sofort im ersten Satz" in note for note in system_notes)
    assert any("sehr einfaches, klares Deutsch" in note for note in system_notes)


def test_generate_chat_reply_answers_simple_math_directly() -> None:
    message = "was ist 2+2?"
    transcript = [{"role": "user", "text": message, "timestamp": "t1"}]

    reply, provider_used, degraded_reason = main.generate_chat_reply(
        message=message,
        level="B2",
        transcript=transcript,
        preferred_provider="rulebased",
    )

    normalized_reply = main.normalize_for_matching(reply)

    assert provider_used == "rulebased"
    assert degraded_reason == "fast_path"
    assert "ist 4" in normalized_reply
    assert "haengt von der situation ab" not in normalized_reply


def test_generate_chat_reply_answers_math_capability_directly() -> None:
    message = "kannst du Math machen?"
    transcript = [{"role": "user", "text": message, "timestamp": "t1"}]

    reply, provider_used, degraded_reason = main.generate_chat_reply(
        message=message,
        level="B2",
        transcript=transcript,
        preferred_provider="rulebased",
    )

    normalized_reply = main.normalize_for_matching(reply)

    assert provider_used == "rulebased"
    assert degraded_reason == "fast_path"
    assert "ja" in normalized_reply
    assert ("matheaufgaben" in normalized_reply) or ("mathe" in normalized_reply)
    assert "haengt von der situation ab" not in normalized_reply


def test_detect_assistant_reply_issue_rejects_vague_hedge_for_basic_direct_question() -> None:
    assert (
        main.detect_assistant_reply_issue("Das haengt von der Situation ab.", "was ist 2+2?")
        == "vague_direct_answer"
    )


def test_generate_chat_reply_fast_path_respects_requested_three_short_sentences() -> None:
    message = "Wie heißt du? Antworte in 3 kurzen Sätzen."
    transcript = [{"role": "user", "text": message, "timestamp": "t1"}]
    constraints = main.extract_chat_reply_constraints(message)

    reply, provider_used, degraded_reason = main.generate_chat_reply(
        message=message,
        level="B2",
        transcript=transcript,
        preferred_provider="rulebased",
    )

    sentences = main.split_complete_assistant_sentences(reply, constraints=constraints)

    assert provider_used == "rulebased"
    assert degraded_reason == "fast_path"
    assert len(sentences) == 3
    assert "du kannst" not in main.normalize_for_matching(reply)
    assert "sag noch" not in main.normalize_for_matching(reply)


def test_generate_chat_reply_simple_german_fast_path_uses_simpler_wording() -> None:
    message = "Wie alt bist du? Bitte kurz und in einfachem Deutsch."
    transcript = [{"role": "user", "text": message, "timestamp": "t1"}]

    reply, provider_used, _ = main.generate_chat_reply(
        message=message,
        level="C1",
        transcript=transcript,
        preferred_provider="rulebased",
    )

    normalized_reply = main.normalize_for_matching(reply)

    assert provider_used == "rulebased"
    assert "kein echtes alter" in normalized_reply
    assert "digitaler sprachpartner" not in normalized_reply


def test_generate_chat_reply_answers_multiple_known_questions_in_order() -> None:
    message = "Wo wohnst du? Wie alt bist du? Antworte in 2 Saetzen."
    transcript = [{"role": "user", "text": message, "timestamp": "t1"}]
    constraints = main.extract_chat_reply_constraints(message)

    reply, provider_used, degraded_reason = main.generate_chat_reply(
        message=message,
        level="B2",
        transcript=transcript,
        preferred_provider="rulebased",
    )

    normalized_reply = main.normalize_for_matching(reply)
    sentences = main.split_complete_assistant_sentences(reply, constraints=constraints)

    assert provider_used == "rulebased"
    assert degraded_reason == "fast_path"
    assert len(sentences) == 2
    assert normalized_reply.index("festen ort") < normalized_reply.index("kein echtes alter")


def test_streamed_chat_does_not_commit_when_client_disconnects_before_completion(monkeypatch) -> None:
    class DummyStreamResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_iter(_response):
        time.sleep(0.15)
        yield {"message": {"content": "Hallo "}}
        time.sleep(0.15)
        yield {"message": {"content": "wie geht es dir?"}}

    client = TestClient(main.app)
    with main.SESSIONS_LOCK:
        main.SESSIONS.clear()

    monkeypatch.setattr(main, "schedule_state_persist", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "resolve_provider", lambda: "ollama")
    monkeypatch.setattr(main, "should_block_rulebased_mode", lambda: False)
    monkeypatch.setattr(main, "OLLAMA_WARMED", True)
    monkeypatch.setattr(main, "open_ollama_chat_stream_response", lambda level, transcript, constraints=None: DummyStreamResponse())
    monkeypatch.setattr(main, "iter_ollama_chat_stream", fake_iter)

    with client.stream(
        "POST",
        "/api/tutor/chat/stream",
        json={"message": "Bitte antworte langsam.", "level": "B2", "mode": "fluidez"},
    ) as response:
        assert response.status_code == 200
        lines = response.iter_lines()
        session_event = json.loads(next(lines))
        thinking_event = json.loads(next(lines))

    assert session_event["type"] == "session"
    assert thinking_event == {"type": "state", "state": "thinking"}
    time.sleep(0.35)
    session = main.get_session_snapshot(session_event["conversation_id"])
    assert session is not None
    assert session["transcript"] == []


def test_streamed_chat_final_only_reply_still_emits_streaming_state(monkeypatch) -> None:
    client = TestClient(main.app)
    with main.SESSIONS_LOCK:
        main.SESSIONS.clear()

    monkeypatch.setattr(main, "schedule_state_persist", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "resolve_provider", lambda: "rulebased")
    monkeypatch.setattr(main, "should_block_rulebased_mode", lambda: False)

    response = client.post(
        "/api/tutor/chat/stream",
        json={"message": "Wie heisst du?", "level": "B2", "mode": "fluidez"},
    )

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert [event["type"] for event in events] == ["session", "state", "state", "final", "done"]
    assert events[1] == {"type": "state", "state": "thinking"}
    assert events[2] == {"type": "state", "state": "streaming"}


def test_streamed_chat_emits_authoritative_sentence_events_for_current_turn(monkeypatch) -> None:
    class DummyStreamResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_iter(_response):
        yield {"message": {"content": "Hallo. "}}
        yield {"message": {"content": "Wie geht es dir?"}}

    client = TestClient(main.app)
    with main.SESSIONS_LOCK:
        main.SESSIONS.clear()

    monkeypatch.setattr(main, "schedule_state_persist", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "resolve_provider", lambda: "ollama")
    monkeypatch.setattr(main, "should_block_rulebased_mode", lambda: False)
    monkeypatch.setattr(main, "OLLAMA_WARMED", True)
    monkeypatch.setattr(main, "open_ollama_chat_stream_response", lambda level, transcript, constraints=None: DummyStreamResponse())
    monkeypatch.setattr(main, "iter_ollama_chat_stream", fake_iter)

    response = client.post(
        "/api/tutor/chat/stream",
        json={"message": "Bitte antworte in zwei Saetzen.", "level": "B2", "mode": "fluidez"},
    )

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    sentence_events = [event for event in events if event["type"] == "sentence"]
    final_event = next(event for event in events if event["type"] == "final")

    assert sentence_events
    assert sentence_events[0]["text"] == "Hallo."
    assert sentence_events[0]["sentence_index"] == 0
    assert events.index(sentence_events[0]) < events.index(final_event)
    assert final_event["text"].startswith(sentence_events[0]["text"])


def test_finish_requires_completed_assistant_turn(monkeypatch) -> None:
    client = TestClient(main.app)
    with main.SESSIONS_LOCK:
        main.SESSIONS.clear()

    monkeypatch.setattr(main, "schedule_state_persist", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "resolve_provider", lambda: "rulebased")
    monkeypatch.setattr(main, "should_block_rulebased_mode", lambda: False)

    conversation_id = "finish-no-assistant"
    main.ensure_session(conversation_id, "B2")
    main.append_transcript(conversation_id, "B2", "user", "Hallo Tutor")

    response = client.post("/api/chat/finish", json={"conversation_id": conversation_id})

    assert response.status_code == 400
    assert "completed assistant turn" in response.json()["detail"]


def test_repo_configuration_no_longer_mentions_paid_providers() -> None:
    env_example = Path(".env.example").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    banned_env_marker = "OPEN" + "AI_"
    banned_vendor = "Open" + "AI"
    banned_product = "Chat" + "GPT"

    assert banned_env_marker not in env_example
    assert banned_vendor not in readme
    assert banned_product not in readme


def test_pick_ollama_chat_model_can_prioritize_fast_model_in_balanced_mode(monkeypatch) -> None:
    monkeypatch.setattr(main, "OLLAMA_SPEED_PRESET", "balanced")
    monkeypatch.setattr(main, "OLLAMA_MODEL", "llama3.2:3b")
    monkeypatch.setattr(main, "OLLAMA_FAST_MODELS", ["llama3.2:1b", "qwen2.5:1.5b"])
    monkeypatch.setattr(main, "ollama_installed_models", lambda: ["llama3.2:3b", "llama3.2:1b"])

    assert main.pick_ollama_chat_model(prefer_fast=True) == "llama3.2:1b"


def test_should_prioritize_fast_ollama_chat_for_early_short_turns() -> None:
    transcript = [{"role": "user", "text": "Wie geht's?", "timestamp": "t1"}]

    assert main.should_prioritize_fast_ollama_chat(transcript) is True


def test_ollama_runtime_probe_detects_models_and_restores_active_model(monkeypatch) -> None:
    class DummyResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "models": [
                        {"name": "llama3.2:3b"},
                        {"name": "llama3.2:1b"},
                    ]
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout=4):
        assert request.full_url.endswith("/api/tags")
        return DummyResponse()

    monkeypatch.setattr(main, "urlopen", fake_urlopen)
    monkeypatch.setattr(main, "OLLAMA_MODEL", "llama3.2:3b")
    monkeypatch.setattr(main, "get_provider_preference", lambda: "ollama")
    main.invalidate_ollama_runtime_cache()

    assert main.ollama_available() is True
    assert main.ollama_installed_models() == ["llama3.2:3b", "llama3.2:1b"]
    assert main.resolve_provider() == "ollama"
    assert main.pick_ollama_chat_model() == "llama3.2:3b"


def test_startup_launcher_exports_runtime_and_waits_for_ready_config() -> None:
    launcher = Path("iniciar_chatbot.bat").read_text(encoding="utf-8")
    local_runner = Path("run_local_servers.py").read_text(encoding="utf-8")
    public_runner = Path("run_public_tunnel.py").read_text(encoding="utf-8")

    assert 'call :read_env OLLAMA_MODEL OLLAMA_MODEL llama3.2:3b' in launcher
    assert 'set "CHAT_PROVIDER=%PROVIDER%"' in launcher
    assert 'set "OLLAMA_MODEL=%OLLAMA_MODEL%"' in launcher
    assert 'set "OLLAMA_BASE_URL=%OLLAMA_BASE_URL%"' in launcher
    assert '--open-url "%URL_PC%"' in launcher
    assert 'start "" "%URL_PC%"' not in launcher
    assert "wait_for_app_readiness(" in local_runner
    assert 'provider == "ollama" and not llm_required and bool(active_model)' in local_runner
    assert "wait_for_app_readiness(" in public_runner


def test_chat_frontend_includes_timeout_busy_state_status_ui_and_tts() -> None:
    frontend = Path("static/assets/app-features.js").read_text(encoding="utf-8")
    helpers = Path("static/assets/app-helpers.js").read_text(encoding="utf-8")
    html = Path("static/index.html").read_text(encoding="utf-8")
    styles = Path("static/assets/styles.css").read_text(encoding="utf-8")
    runtime = Path("static/assets/tutor-runtime.js").read_text(encoding="utf-8")

    assert "window.setChatStatus = function setChatStatus" in frontend
    assert "window.updateChatComposerState = function updateChatComposerState()" in frontend
    assert "window.toggleChatTts = function toggleChatTts()" in frontend
    assert "window.speakChatReply = function speakChatReply(text)" in frontend
    assert "window.repeatLastChatReply = function repeatLastChatReply()" in frontend
    assert "window.persistChatVoicePreferences = function persistChatVoicePreferences()" in frontend
    assert "window.getChatRegionalVoiceOptions = function getChatRegionalVoiceOptions()" in frontend
    assert "window.startBrowserDictation = function startBrowserDictation(target)" in frontend
    assert "window.toggleVoiceInput = async function toggleVoiceInput(target)" in frontend
    assert "window.focusVoiceInputFallback = function focusVoiceInputFallback(target)" in frontend
    assert "webkitSpeechRecognition" in frontend or "window.webkitSpeechRecognition" in frontend
    assert "SpeechSynthesisUtterance" in frontend
    assert "state.chatRequestInFlight = true;" in frontend
    assert "timeoutMs: state.config?.chat_timeout_ms || 45000" in frontend
    assert "state.chatTranscribeInFlight = true;" in frontend
    assert "window.apiFetch = async function apiFetch(url, options = {})" in helpers
    assert "AbortController()" in helpers
    assert 'chatRequestInFlight: false' in helpers
    assert 'speechRecognition: null' in helpers
    assert 'speechRecognitionActive: false' in helpers
    assert 'chatTtsEnabled: true' in helpers
    assert 'chatHasCompletedAssistantTurn: false' in helpers
    assert 'chatVoiceGender: "female"' in helpers
    assert 'chatVoiceVariant: "standard"' in helpers
    assert 'chat_tts_on: "Audio an"' in helpers
    assert "els.chatFinishBtn.disabled = busy || !state.chatHasCompletedAssistantTurn;" in frontend
    assert "state.chatHasCompletedAssistantTurn = true;" in frontend
    assert "state.chatHasCompletedAssistantTurn = true;" in runtime
    assert "/api/tutor/chat/commit" in runtime
    assert 'id="chatStatus"' in html
    assert 'id="chatTtsBtn"' in html
    assert 'class="mic-icon-btn"' in html
    assert 'id="chatVoiceGender"' in html
    assert 'id="chatVoiceVariant"' in html
    assert 'id="chatVoiceRegion"' in html
    assert 'id="profileTutorVoiceGender"' in html
    assert 'id="chatReplayBtn"' in html
    assert 'id="chatMicBtn"' in html
    assert 'id="tutorAvatarStage"' not in html
    assert 'tutor-avatar.js' not in html
    assert 'data-tutor-avatar=' not in html
    assert 'data-profile-avatar=' not in html
    assert ".voice-control-grid" in styles
    assert ".mic-icon-btn" in styles
    assert ".bubble.pending" in styles
