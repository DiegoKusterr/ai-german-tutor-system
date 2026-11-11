"""Offline synthetic Ollama transport tests; no model or browser is run."""
import asyncio
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main


PROMPT = "Beschreibe eine erfundene Buchhandlung und stelle eine Frage."


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "SESSIONS", {})
    monkeypatch.setattr(main, "schedule_state_persist", lambda *a, **kw: None)
    monkeypatch.setattr(main, "resolve_provider", lambda: "ollama")
    monkeypatch.setattr(main, "OLLAMA_WARMED", True)
    for helper in ("maybe_direct_question_bundle_reply", "maybe_personal_answer", "maybe_smalltalk_reply"):
        monkeypatch.setattr(main, helper, lambda *a, **kw: None)
    return TestClient(main.app)


def mock_stream(monkeypatch, chunks, reason="stop", error=None):
    payloads = [{"message": {"content": chunk}, "done": False} for chunk in chunks]
    if error:
        payloads.append({"error": error})
    else:
        payloads.append({"done": True, "done_reason": reason, "message": {"content": ""}})
    response = io.BytesIO(b"\n".join(json.dumps(item, ensure_ascii=False).encode("utf-8") for item in payloads))
    monkeypatch.setattr(main, "open_ollama_chat_stream_response", lambda *a, **kw: response)
    return response


def events_from(client):
    response = client.post("/api/tutor/chat/stream", json={"message": PROMPT, "level": "B2"})
    assert response.status_code == 200
    return [json.loads(line) for line in response.text.splitlines()]


@pytest.mark.parametrize("reason,chunks", [
    ("length", ['Sie sagt: "Ich ', 'lerne Deutsch.', '" ', 'Und was möchtest du']),
    ("length", ['Die Buchhandlung ist ruhig. ', 'Was würdest du gern']),
    ("stop", ['Sie sagt: „Ich lerne Deutsch.“ ', 'Was liest du?']),
    ("stop", ['Er fragt: “Was liest du?”']),
    ("stop", ['Sie sagt: «Ich lerne Deutsch.»']),
    (None, ['Ein kurzer Text ohne Schlusszeichen']),
])
def test_stream_final_commit_and_disk_history_preserve_exact_text(client, monkeypatch, tmp_path, reason, chunks):
    transport = mock_stream(monkeypatch, chunks, reason)
    events = events_from(client)
    final = next(item for item in events if item["type"] == "final")
    done = next(item for item in events if item["type"] == "done")
    expected = "".join(chunks).strip()
    assert transport.closed
    assert "".join(item["text"] for item in events if item["type"] == "delta").strip() == expected
    assert final["text"] == expected
    assert final["provider"] == done["provider"] == "ollama"
    for item in (final, done):
        assert item["finish_reason"] == reason
        assert item["truncated"] is (reason == "length")
    sentences = [item["text"] for item in events if item["type"] == "sentence"]
    assert expected.startswith(" ".join(sentences))
    assert "Und was möchtest du" not in sentences
    assert "Was würdest du gern" not in sentences
    session = main.get_session_snapshot(done["conversation_id"])
    assert session["transcript"] == []  # Streaming still requires explicit client commit.
    body = {"conversation_id": done["conversation_id"], "message": PROMPT,
            "reply": final["text"], "level": "B2", "finish_reason": done["finish_reason"]}
    for _ in range(2):
        assert client.post("/api/tutor/chat/commit", json=body).status_code == 200
    stored = main.get_active_transcript(main.get_session_snapshot(done["conversation_id"]))
    assert len(stored) == 2  # Duplicate commit remains idempotent.
    assert stored[-1]["text"] == expected
    assert stored[-1]["meta"]["source"] == "streamed"
    if reason is not None:
        assert stored[-1]["meta"]["finish_reason"] == reason
        assert stored[-1]["meta"]["truncated"] is (reason == "length")
    monkeypatch.setattr(main, "STATE_FILE", tmp_path / "synthetic-state.json")
    main.persist_state_to_disk()
    main.SESSIONS.clear()
    main.load_state_from_disk()
    restored = main.get_active_transcript(main.get_session_snapshot(done["conversation_id"]))
    assert restored == stored


@pytest.mark.parametrize("quote", [('"', '"'), ('„', '“'), ('“', '”'), ('«', '»')])
def test_sentence_events_wait_for_closing_quotation_mark(client, monkeypatch, quote):
    opening, closing = quote
    mock_stream(monkeypatch, [f"Sie sagt: {opening}Ich lerne Deutsch.", closing, " ", "Und du?"])
    events = events_from(client)
    first_sentence_index = next(i for i, item in enumerate(events) if item["type"] == "sentence")
    close_index = next(i for i, item in enumerate(events) if item["type"] == "delta" and item["text"] == closing)
    assert first_sentence_index > close_index
    assert events[first_sentence_index]["text"] == f"Sie sagt: {opening}Ich lerne Deutsch.{closing}"


@pytest.mark.parametrize("reply", [
    'Das Beispiel lautet: "Ich lerne Deutsch."',
    'Das Beispiel lautet: „Ich lerne Deutsch.“',
    'Die Buchhandlung ist ruhig. Und was möchtest du',
])
def test_finalizer_preserves_quotes_and_incomplete_followup(reply):
    assert main.finalize_assistant_reply(reply) == reply


def test_native_stream_does_not_apply_a_second_word_or_sentence_limit(client, monkeypatch):
    reply = " ".join(f"Im Regal steht das erfundene Buch Nummer {number}." for number in range(12))
    mock_stream(monkeypatch, [reply])
    events = events_from(client)
    assert next(item["text"] for item in events if item["type"] == "final") == reply
    assert len([item for item in events if item["type"] == "sentence"]) == 12


@pytest.mark.parametrize("endpoint", ["/chat", "/api/chat"])
@pytest.mark.parametrize("reason", ["stop", "length"])
def test_blocking_api_reports_length_and_preserves_reply(client, monkeypatch, endpoint, reason):
    reply = 'Sie sagt: "Ich lese ein Buch." Und was möchtest du'
    monkeypatch.setattr(main, "pick_ollama_chat_model", lambda: "llama3.2:1b")
    monkeypatch.setattr(main, "http_post_json", lambda *a, **kw: {"message": {"content": reply}, "done_reason": reason})
    response = client.post(endpoint, json={"message": PROMPT, "level": "B2"})
    assert response.status_code == 200
    result = response.json()
    assert result["reply"] == reply
    assert result["finish_reason"] == reason
    assert result["truncated"] is (reason == "length")
    stored = main.get_active_transcript(main.get_session_snapshot(result["conversation_id"]))[-1]
    assert stored["text"] == reply
    assert stored["meta"]["truncated"] is (reason == "length")


@pytest.mark.parametrize("preset", ["balanced", "quality", "turbo"])
@pytest.mark.parametrize("budget", [72, 160])
def test_configured_generation_budget_is_not_replaced_by_48(monkeypatch, preset, budget):
    requests = []
    monkeypatch.setattr(main, "OLLAMA_SPEED_PRESET", preset)
    monkeypatch.setattr(main, "OLLAMA_CHAT_MAX_TOKENS", budget)
    monkeypatch.setattr(main, "pick_ollama_chat_model", lambda: "llama3.2:1b")
    def post(url, payload, **kwargs):
        requests.append(payload)
        return {"message": {"content": "Eine erfundene Antwort."}}
    def open_response(request, **kwargs):
        requests.append(json.loads(request.data))
        return io.BytesIO()
    monkeypatch.setattr(main, "http_post_json", post)
    monkeypatch.setattr(main, "urlopen", open_response)
    for turns in (1, 5):
        transcript = [{"role": "user", "text": PROMPT, "timestamp": str(i)} for i in range(turns)]
        main.chat_with_ollama("B2", transcript)
        main.open_ollama_chat_stream_response("B2", transcript).close()
    assert len(requests) == 4
    assert all(item["options"]["num_predict"] == budget for item in requests)


@pytest.mark.parametrize("error_kind", ["native", "json", "timeout", "empty"])
def test_stream_errors_do_not_emit_success_or_commit_partial_reply(client, monkeypatch, error_kind):
    if error_kind == "native":
        response = mock_stream(monkeypatch, ["Ein Teil "], error="Synthetic runner failure")
    else:
        class FailingResponse(io.BytesIO):
            def readline(self, *args):
                if error_kind == "timeout":
                    raise TimeoutError("synthetic timeout")
                return super().readline(*args)
        response = FailingResponse(b"invalid json\n" if error_kind == "json" else b"")
        monkeypatch.setattr(main, "open_ollama_chat_stream_response", lambda *a, **kw: response)
    events = events_from(client)
    assert response.closed
    assert any(item["type"] == "error" for item in events)
    assert not any(item["type"] in {"final", "done"} for item in events)
    session_id = next(item["conversation_id"] for item in events if item["type"] == "session")
    assert main.get_session_snapshot(session_id)["transcript"] == []


def test_explicit_stream_cancellation_closes_transport_without_commit(client, monkeypatch):
    response = mock_stream(monkeypatch, ["Ein Teil ", "der Antwort."])
    class Request:
        async def is_disconnected(self):
            return False
    async def cancel():
        stream = await main.api_tutor_chat_stream(main.TutorStreamRequest(message=PROMPT, level="B2"), Request())
        iterator = stream.body_iterator
        events = []
        async for line in iterator:
            event = json.loads(line)
            events.append(event)
            if event["type"] == "delta":
                await iterator.aclose()
                break
        return events
    events = asyncio.run(cancel())
    assert response.closed
    assert not any(item["type"] == "done" for item in events)
    assert main.get_session_snapshot(events[0]["conversation_id"])["transcript"] == []


def test_browser_source_forwards_finish_reason_and_discloses_truncation():
    # Source contract only: actual browser rendering remains a manual check.
    source = Path("static/assets/tutor-runtime.js").read_text(encoding="utf-8")
    assert "finishReason: event.finish_reason" in source
    assert "finish_reason: finishReason || null" in source
    assert "event.truncated" in source
    assert "Antwort am Tokenlimit abgebrochen" in source
