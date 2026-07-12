from __future__ import annotations

import hashlib
import json
import os
import re
import socket
from time import monotonic
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CHAT_PROVIDER = os.getenv("CHAT_PROVIDER", "ollama").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
EXAM_MOCK_OLLAMA_MODEL_ENV = os.getenv("EXAM_MOCK_OLLAMA_MODEL")
OLLAMA_MODEL = (
    (EXAM_MOCK_OLLAMA_MODEL_ENV.strip() if EXAM_MOCK_OLLAMA_MODEL_ENV else "")
    or os.getenv("OLLAMA_MODEL", "llama3.2:3b").strip()
    or "llama3.2:3b"
)
EXAM_MOCK_OLLAMA_MODELS = os.getenv("EXAM_MOCK_OLLAMA_MODELS", "").strip()
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m").strip() or "30m"
OLLAMA_FAST_MODELS = [
    item.strip()
    for item in os.getenv(
        "OLLAMA_FAST_MODELS",
        "llama3.2:1b,qwen2.5:1.5b,llama3.2:3b,gemma2:2b,phi3:mini,mistral:7b",
    ).split(",")
    if item.strip()
]
OLLAMA_PULL_FAST_MODEL = os.getenv(
    "OLLAMA_PULL_FAST_MODEL",
    OLLAMA_FAST_MODELS[0] if OLLAMA_FAST_MODELS else "llama3.2:1b",
).strip()
EXAM_MOCK_LLM_ENABLED = os.getenv("EXAM_MOCK_LLM_ENABLED", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
    "si",
    "sí",
}

try:
    OLLAMA_TIMEOUT = int(os.getenv("EXAM_MOCK_OLLAMA_TIMEOUT", "12").strip())
except ValueError:
    OLLAMA_TIMEOUT = 12
OLLAMA_TIMEOUT = max(8, min(OLLAMA_TIMEOUT, 90))

_AVAILABLE_MODELS_CACHE: dict[str, Any] = {"expires_at": 0.0, "value": []}
_AVAILABLE_MODELS_CACHE_TTL_SEC = 15.0


def _dedupe_models(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        model_name = str(value or "").strip()
        if not model_name:
            continue
        key = model_name.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(model_name)
    return result


def _configured_exam_mock_models() -> list[str]:
    if EXAM_MOCK_OLLAMA_MODELS:
        return _dedupe_models(EXAM_MOCK_OLLAMA_MODELS.split(","))
    if EXAM_MOCK_OLLAMA_MODEL_ENV:
        return _dedupe_models(
            [
                OLLAMA_MODEL,
                OLLAMA_PULL_FAST_MODEL,
                *OLLAMA_FAST_MODELS,
                os.getenv("OLLAMA_MODEL", "").strip(),
                "llama3.2:1b",
            ]
        )
    return _dedupe_models(
        [
            OLLAMA_PULL_FAST_MODEL,
            "llama3.2:1b",
            *OLLAMA_FAST_MODELS,
            OLLAMA_MODEL,
            os.getenv("OLLAMA_MODEL", "").strip(),
            "llama3.2:3b",
        ]
    )


def _model_speed_rank(model_name: str) -> tuple[int, int, str]:
    lower = model_name.lower()
    size_markers = [
        "0.5b",
        "1b",
        "1.5b",
        "2b",
        "3b",
        "4b",
        "7b",
        "8b",
        "9b",
        "13b",
        "14b",
    ]
    size_rank = len(size_markers) + 5
    for index, marker in enumerate(size_markers):
        if marker in lower:
            size_rank = index
            break
    fast_hint = 0 if model_name in {OLLAMA_PULL_FAST_MODEL, *OLLAMA_FAST_MODELS} else 1
    return (size_rank, fast_hint, lower)


def _available_ollama_models() -> list[str]:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return []
    now = monotonic()
    cached_value = _AVAILABLE_MODELS_CACHE.get("value", [])
    if now < float(_AVAILABLE_MODELS_CACHE.get("expires_at", 0.0)) and isinstance(cached_value, list):
        return list(cached_value)
    try:
        request = Request(url=f"{OLLAMA_BASE_URL}/api/tags", method="GET")
        with urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = [
            str(item.get("name", "")).strip()
            for item in payload.get("models", [])
            if str(item.get("name", "")).strip()
        ]
    except Exception:
        models = []
    _AVAILABLE_MODELS_CACHE["value"] = models
    _AVAILABLE_MODELS_CACHE["expires_at"] = now + _AVAILABLE_MODELS_CACHE_TTL_SEC
    return list(models)


def choose_exam_mock_ollama_models(available_models: Iterable[str] | None = None) -> list[str]:
    configured = _configured_exam_mock_models()
    if available_models is None:
        available = _available_ollama_models()
    else:
        available = _dedupe_models(available_models)
    if not available:
        return configured

    installed_lookup = {model.lower(): model for model in available}
    selected = [installed_lookup[item.lower()] for item in configured if item.lower() in installed_lookup]
    if selected:
        return _dedupe_models(selected)
    return sorted(available, key=_model_speed_rank)


def _http_post_json(url: str, payload: dict[str, Any], timeout: int = OLLAMA_TIMEOUT) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        url=url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"Ollama timeout after {timeout}s.") from exc
    except URLError as exc:
        raise RuntimeError(f"Ollama not reachable: {exc.reason}") from exc
    except OSError as exc:
        raise RuntimeError(f"Ollama network error: {exc}") from exc
    return json.loads(raw)


def ollama_available() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    if not EXAM_MOCK_LLM_ENABLED or CHAT_PROVIDER != "ollama":
        return False
    return bool(choose_exam_mock_ollama_models())


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        candidate = cleaned[start : end + 1]
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    raise RuntimeError("LLM did not return valid JSON.")


def stable_seed_int(seed_key: str) -> int:
    digest = hashlib.sha256(seed_key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _build_generate_payload(prompt: str, *, model_name: str, seed_key: str, max_tokens: int) -> dict[str, Any]:
    return {
        "model": model_name,
        "stream": False,
        "format": "json",
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "temperature": 0.12,
            "top_p": 0.85,
            "repeat_penalty": 1.03,
            "num_ctx": 2304,
            "num_predict": max(220, min(int(max_tokens), 1100)),
            "seed": stable_seed_int(seed_key),
        },
        "prompt": (
            "SYSTEM:\n"
            "Du erzeugst originale Goethe-inspirierte Pruefungsinhalte. "
            "Nutze nur die gegebene Struktur als Blueprint. "
            "Kopiere niemals offizielles Material. "
            "Antworte ausschliesslich mit kompaktem, gueltigem JSON.\n\n"
            "USER:\n"
            f"{prompt}"
        ),
    }


def _build_chat_payload(prompt: str, *, model_name: str, seed_key: str, max_tokens: int) -> dict[str, Any]:
    return {
        "model": model_name,
        "stream": False,
        "format": "json",
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "temperature": 0.08,
            "top_p": 0.82,
            "repeat_penalty": 1.02,
            "num_ctx": 2048,
            "num_predict": max(120, min(int(max_tokens), 320)),
            # Short JSON briefs are far more stable with a fixed seed; the prompt
            # already varies by module/variant and provides the needed diversity.
            "seed": stable_seed_int("exam-mock-json-brief"),
        },
        "messages": [
            {
                "role": "system",
                "content": "Antworte ausschliesslich mit kompaktem, gueltigem JSON ohne Markdown oder Zusatztext.",
            },
            {"role": "user", "content": prompt},
        ],
    }


def generate_structured_exam_part(
    prompt: str,
    *,
    seed_key: str,
    max_tokens: int = 1400,
    timeout_sec: int | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    if not ollama_available():
        return None, None

    errors: list[str] = []
    candidate_models = choose_exam_mock_ollama_models()
    use_chat_endpoint = int(max_tokens) <= 220
    request_timeout = max(4, int(timeout_sec or OLLAMA_TIMEOUT))
    for index, model_name in enumerate(candidate_models):
        payload = (
            _build_chat_payload(prompt, model_name=model_name, seed_key=seed_key, max_tokens=max_tokens)
            if use_chat_endpoint
            else _build_generate_payload(prompt, model_name=model_name, seed_key=seed_key, max_tokens=max_tokens)
        )
        try:
            endpoint = "/api/chat" if use_chat_endpoint else "/api/generate"
            response = _http_post_json(f"{OLLAMA_BASE_URL}{endpoint}", payload, timeout=request_timeout)
            raw_text = str(response.get("response", "")).strip() or str(response.get("message", {}).get("content", "")).strip()
            if not raw_text:
                raise RuntimeError("Empty JSON response from local exam generator.")
            return _extract_json_object(raw_text), model_name
        except Exception as exc:
            errors.append(f"{model_name}: {exc}")
            lower_error = str(exc).lower()
            remaining_models = candidate_models[index + 1 :]
            if "timeout" in lower_error and remaining_models:
                current_rank = _model_speed_rank(model_name)
                if all(_model_speed_rank(other) >= current_rank for other in remaining_models):
                    break
    raise RuntimeError(" ; ".join(errors[:4]) if errors else "No local exam model could generate a valid part.")
