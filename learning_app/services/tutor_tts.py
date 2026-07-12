from __future__ import annotations

import io
import os
import re
import wave
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

try:
    from piper import PiperVoice
except Exception:  # pragma: no cover - optional local TTS dependency
    PiperVoice = None


BASE_DIR = Path(__file__).resolve().parents[2]
_WHITESPACE_RE = re.compile(r"\s+")
_VOICE_CACHE_LOCK = Lock()
_VOICE_CACHE_KEY = ""
_VOICE_CACHE_INSTANCE: Any | None = None
STRICT_IDENTITY_PERSONA_KEYS = {"woman", "man"}

TUTOR_TTS_PROVIDER = os.getenv("TUTOR_TTS_PROVIDER", "piper").strip().lower() or "none"
TUTOR_TTS_FALLBACK = os.getenv("TUTOR_TTS_FALLBACK", "browser").strip().lower() or "browser"
TUTOR_TTS_VOICE = os.getenv("TUTOR_TTS_VOICE", "de_DE-thorsten-medium").strip() or "de_DE-thorsten-medium"
TUTOR_TTS_MODEL_PATH = os.getenv(
    "TUTOR_TTS_MODEL_PATH",
    "data/tts/voices/de_DE-thorsten-medium.onnx",
).strip()
TUTOR_TTS_CONFIG_PATH = os.getenv(
    "TUTOR_TTS_CONFIG_PATH",
    "data/tts/voices/de_DE-thorsten-medium.onnx.json",
).strip()
TUTOR_TTS_MAX_CHARS = max(80, int(os.getenv("TUTOR_TTS_MAX_CHARS", "280") or 280))
TUTOR_TTS_PERSONA_ENV_MAP = {
    "studio": (
        {
            "voice": "TUTOR_TTS_STUDIO_VOICE",
            "model_path": "TUTOR_TTS_STUDIO_MODEL_PATH",
            "config_path": "TUTOR_TTS_STUDIO_CONFIG_PATH",
        },
    ),
    "coach": (
        {
            "voice": "TUTOR_TTS_COACH_VOICE",
            "model_path": "TUTOR_TTS_COACH_MODEL_PATH",
            "config_path": "TUTOR_TTS_COACH_CONFIG_PATH",
        },
    ),
    "examiner": (
        {
            "voice": "TUTOR_TTS_EXAMINER_VOICE",
            "model_path": "TUTOR_TTS_EXAMINER_MODEL_PATH",
            "config_path": "TUTOR_TTS_EXAMINER_CONFIG_PATH",
        },
    ),
    "woman": (
        {
            "voice": "TUTOR_TTS_WOMAN_VOICE",
            "model_path": "TUTOR_TTS_WOMAN_MODEL_PATH",
            "config_path": "TUTOR_TTS_WOMAN_CONFIG_PATH",
        },
        {
            "voice": "TUTOR_TTS_STUDIO_VOICE",
            "model_path": "TUTOR_TTS_STUDIO_MODEL_PATH",
            "config_path": "TUTOR_TTS_STUDIO_CONFIG_PATH",
        },
    ),
    "man": (
        {
            "voice": "TUTOR_TTS_MAN_VOICE",
            "model_path": "TUTOR_TTS_MAN_MODEL_PATH",
            "config_path": "TUTOR_TTS_MAN_CONFIG_PATH",
        },
        {
            "voice": "TUTOR_TTS_COACH_VOICE",
            "model_path": "TUTOR_TTS_COACH_MODEL_PATH",
            "config_path": "TUTOR_TTS_COACH_CONFIG_PATH",
        },
        {
            "voice": "TUTOR_TTS_EXAMINER_VOICE",
            "model_path": "TUTOR_TTS_EXAMINER_MODEL_PATH",
            "config_path": "TUTOR_TTS_EXAMINER_CONFIG_PATH",
        },
    ),
}


@dataclass(frozen=True)
class TutorTtsStatus:
    available: bool
    provider: str = "none"
    fallback: str = "browser"
    voice_label: str | None = None
    voice_source: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class TutorTtsVoiceBundle:
    voice_label: str
    model_path: Path | None
    config_path: Path | None
    source: str = "global"


def _resolve_optional_path(raw_path: str) -> Path | None:
    raw_value = str(raw_path or "").strip()
    if not raw_value:
        return None
    candidate = Path(raw_value)
    if not candidate.is_absolute():
        candidate = BASE_DIR / candidate
    return candidate


def _normalize_persona_key(value: str | None) -> str | None:
    key = str(value or "").strip().lower()
    return key if key in TUTOR_TTS_PERSONA_ENV_MAP else None


def _requires_identity_locked_voice(persona_key: str | None) -> bool:
    return _normalize_persona_key(persona_key) in STRICT_IDENTITY_PERSONA_KEYS


def _build_voice_bundle(
    *,
    voice_label: str,
    model_path: str,
    config_path: str,
    source: str,
) -> TutorTtsVoiceBundle:
    resolved_voice_label = str(voice_label or "").strip() or TUTOR_TTS_VOICE
    return TutorTtsVoiceBundle(
        voice_label=resolved_voice_label,
        model_path=_resolve_optional_path(model_path),
        config_path=_resolve_optional_path(config_path),
        source=source,
    )


def _build_global_voice_bundle() -> TutorTtsVoiceBundle:
    return _build_voice_bundle(
        voice_label=TUTOR_TTS_VOICE,
        model_path=TUTOR_TTS_MODEL_PATH,
        config_path=TUTOR_TTS_CONFIG_PATH,
        source="global",
    )


def _build_persona_voice_bundles(persona_key: str | None) -> list[TutorTtsVoiceBundle]:
    normalized_persona = _normalize_persona_key(persona_key)
    if not normalized_persona:
        return []
    bundles: list[TutorTtsVoiceBundle] = []
    for env_map in TUTOR_TTS_PERSONA_ENV_MAP[normalized_persona]:
        voice_label = os.getenv(env_map["voice"], "").strip()
        model_path = os.getenv(env_map["model_path"], "").strip()
        config_path = os.getenv(env_map["config_path"], "").strip()
        if not any([voice_label, model_path, config_path]):
            continue
        bundles.append(
            _build_voice_bundle(
                voice_label=voice_label,
                model_path=model_path,
                config_path=config_path,
                source=f"persona:{normalized_persona}",
            )
        )
    return bundles


def _get_voice_bundle_error(bundle: TutorTtsVoiceBundle | None) -> str:
    if not bundle or not bundle.model_path or not bundle.model_path.exists():
        return "Tutor TTS model file is missing."
    if bundle.config_path and not bundle.config_path.exists():
        return "Tutor TTS config file is missing."
    return ""


def _resolve_voice_bundle(persona_key: str | None = None) -> tuple[TutorTtsVoiceBundle | None, str]:
    for persona_bundle in _build_persona_voice_bundles(persona_key):
        persona_error = _get_voice_bundle_error(persona_bundle)
        if not persona_error:
            return persona_bundle, ""

    if _requires_identity_locked_voice(persona_key):
        normalized_persona = _normalize_persona_key(persona_key) or "selected"
        return None, f"Local Tutor TTS voice is not configured for the selected tutor identity ({normalized_persona})."

    global_bundle = _build_global_voice_bundle()
    global_error = _get_voice_bundle_error(global_bundle)
    if not global_error:
        return global_bundle, ""
    return None, global_error


def normalize_tutor_tts_text(text: str) -> str:
    cleaned = _WHITESPACE_RE.sub(" ", str(text or "").replace("\r", " ").replace("\n", " ")).strip()
    if len(cleaned) > TUTOR_TTS_MAX_CHARS:
        cleaned = cleaned[:TUTOR_TTS_MAX_CHARS].rstrip()
    return cleaned


def get_tutor_tts_status(persona_key: str | None = None) -> TutorTtsStatus:
    if TUTOR_TTS_PROVIDER in {"", "none", "off", "disabled"}:
        return TutorTtsStatus(
            available=False,
            provider="none",
            fallback=TUTOR_TTS_FALLBACK,
            voice_label=TUTOR_TTS_VOICE,
            voice_source="global",
            detail="Local Tutor TTS is disabled.",
        )
    if TUTOR_TTS_PROVIDER != "piper":
        return TutorTtsStatus(
            available=False,
            provider="none",
            fallback=TUTOR_TTS_FALLBACK,
            voice_label=TUTOR_TTS_VOICE,
            voice_source="global",
            detail=f"Unsupported Tutor TTS provider: {TUTOR_TTS_PROVIDER}",
        )
    if PiperVoice is None:
        return TutorTtsStatus(
            available=False,
            provider="none",
            fallback=TUTOR_TTS_FALLBACK,
            voice_label=TUTOR_TTS_VOICE,
            voice_source="global",
            detail="Piper is not installed.",
        )

    bundle, bundle_error = _resolve_voice_bundle(persona_key)
    if bundle_error or not bundle:
        return TutorTtsStatus(
            available=False,
            provider="none",
            fallback=TUTOR_TTS_FALLBACK,
            voice_label=bundle.voice_label if bundle else None,
            voice_source=bundle.source if bundle else None,
            detail=bundle_error or "Tutor TTS is unavailable.",
        )

    return TutorTtsStatus(
        available=True,
        provider="local",
        fallback=TUTOR_TTS_FALLBACK,
        voice_label=bundle.voice_label,
        voice_source=bundle.source,
        detail="Local Tutor TTS is ready.",
    )


def clear_tutor_tts_cache() -> None:
    global _VOICE_CACHE_KEY, _VOICE_CACHE_INSTANCE
    with _VOICE_CACHE_LOCK:
        _VOICE_CACHE_KEY = ""
        _VOICE_CACHE_INSTANCE = None


def _load_voice(persona_key: str | None = None) -> Any:
    global _VOICE_CACHE_KEY, _VOICE_CACHE_INSTANCE
    status = get_tutor_tts_status(persona_key)
    if not status.available:
        raise RuntimeError(status.detail or "Local Tutor TTS is unavailable.")

    bundle, _ = _resolve_voice_bundle(persona_key)
    if not bundle:
        raise RuntimeError("Local Tutor TTS is unavailable.")
    model_path = bundle.model_path
    config_path = bundle.config_path
    cache_key = "|".join(
        [
            str(model_path or ""),
            str(config_path or ""),
            bundle.voice_label,
        ]
    )

    with _VOICE_CACHE_LOCK:
        if _VOICE_CACHE_INSTANCE is not None and _VOICE_CACHE_KEY == cache_key:
            return _VOICE_CACHE_INSTANCE

        voice = PiperVoice.load(
            model_path=str(model_path),
            config_path=str(config_path) if config_path else None,
            use_cuda=False,
        )
        _VOICE_CACHE_INSTANCE = voice
        _VOICE_CACHE_KEY = cache_key
        return voice


def synthesize_tutor_tts(text: str, persona_key: str | None = None) -> tuple[bytes, str]:
    normalized_text = normalize_tutor_tts_text(text)
    if not normalized_text:
        raise RuntimeError("Tutor TTS text is empty.")

    voice = _load_voice(persona_key)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        voice.synthesize_wav(normalized_text, wav_file)

    audio_bytes = buffer.getvalue()
    if len(audio_bytes) <= 44:
        raise RuntimeError("Tutor TTS produced empty audio.")
    return audio_bytes, normalized_text
