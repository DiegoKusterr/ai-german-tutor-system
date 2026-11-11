"""Inspect mocked requests; these tests do not run Ollama or measure performance."""
import json
from pathlib import Path

import pytest

import main


def transcript(turns):
    entries = []
    for number in range(turns):
        entries.append({"role": "user", "text": "Eine erfundene Bestellung für die Buchhandlung.", "timestamp": str(number)})
        if number < turns-1:
            entries.append({"role": "assistant", "text": "Wir üben eine fiktive Bestellung.", "timestamp": str(number)})
    return entries


@pytest.mark.parametrize("preset,model,context,expected_model,expected_context", [
    ("quality", "llama3.2:1b", 1280, "llama3.2:1b", 1280),
    ("quality", "llama3.2:3b", 2048, "llama3.2:3b", 2048),
    ("balanced", "llama3.2:3b", 2048, "llama3.2:3b", 2048),
    ("balanced", "llama3.2:1b", 1280, "llama3.2:1b", 1280),
    ("quality", "llama3.2:3b", 4096, "llama3.2:3b", 2048),
    ("turbo", "llama3.2:3b", 4096, "llama3.2:1b", 1280),
])
def test_warmup_blocking_and_stream_requests_keep_runner_options_consistent(
    monkeypatch, preset, model, context, expected_model, expected_context
):
    requests = []
    monkeypatch.setattr(main, "OLLAMA_SPEED_PRESET", preset)
    monkeypatch.setattr(main, "OLLAMA_MODEL", model)
    monkeypatch.setattr(main, "OLLAMA_NUM_CTX", context)
    monkeypatch.setattr(main, "OLLAMA_NUM_THREAD", 4)
    monkeypatch.setattr(main, "OLLAMA_KEEP_ALIVE", "30m")
    monkeypatch.setattr(main, "OLLAMA_CHAT_MAX_TOKENS", 96)
    monkeypatch.setattr(main, "OLLAMA_WARMED", False)
    monkeypatch.setattr(main, "OLLAMA_FAST_MODELS", ["llama3.2:1b", "llama3.2:3b"])
    monkeypatch.setattr(main, "ollama_installed_models", lambda: ["llama3.2:3b", "llama3.2:1b"])

    def post(url, payload, **kwargs):
        assert url == main.OLLAMA_BASE_URL+"/api/chat"
        requests.append(payload)
        return {"message": {"content": "Eine fiktive Antwort."}}

    class Response:
        def close(self):
            pass

    def open_response(request, **kwargs):
        requests.append(json.loads(request.data))
        return Response()

    monkeypatch.setattr(main, "http_post_json", post)
    monkeypatch.setattr(main, "urlopen", open_response)
    main.warmup_ollama_once()
    assert main.OLLAMA_WARMED
    for turns in [1, 2, 5]:
        main.chat_with_ollama("B2", transcript(turns))
        main.open_ollama_chat_stream_response("B2", transcript(turns)).close()

    assert len(requests) == 7
    reference = {key: value for key, value in requests[0]["options"].items() if key != "num_predict"}
    assert reference["num_ctx"] == expected_context
    assert reference["num_thread"] == 4
    assert requests[0]["options"]["num_predict"] == 1
    for request in requests:
        assert request["model"] == expected_model
        assert request["keep_alive"] == "30m"
        assert {key: value for key, value in request["options"].items() if key != "num_predict"} == reference
    # Prompt/history grows, while runtime options do not depend on turn count.
    assert [item["stream"] for item in requests] == [False, False, True, False, True, False, True]


def test_example_supports_low_resource_profile_and_preserves_3b_alternative():
    text = Path(".env.example").read_text(encoding="utf-8")
    active = dict(line.split("=", 1) for line in text.splitlines() if "=" in line and not line.startswith("#"))
    assert active["OLLAMA_MODEL"] == "llama3.2:1b"
    assert active["OLLAMA_NUM_CTX"] == "1280"
    assert active["OLLAMA_NUM_THREAD"] == "4"
    assert active["OLLAMA_KEEP_ALIVE"] == "30m"
    assert active["OLLAMA_SPEED_PRESET"] == "quality"
    assert "Alternative: OLLAMA_MODEL=llama3.2:3b" in text
