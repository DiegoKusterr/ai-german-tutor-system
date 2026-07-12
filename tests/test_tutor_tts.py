from __future__ import annotations

from pathlib import Path

import main
from fastapi.testclient import TestClient

import learning_app.services.tutor_tts as tutor_tts
from learning_app.services.tutor_tts import TutorTtsStatus


def _build_wav_bytes() -> bytes:
  return (
    b"RIFF$\x00\x00\x00WAVEfmt "
    b"\x10\x00\x00\x00\x01\x00\x01\x00"
    b"\x22\x56\x00\x00\x44\xac\x00\x00"
    b"\x02\x00\x10\x00data\x00\x00\x00\x00"
  )


def test_tutor_tts_status_reports_disabled_provider(monkeypatch) -> None:
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_PROVIDER", "none")
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_FALLBACK", "browser")
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_VOICE", "de_DE-thorsten-medium")

  status = tutor_tts.get_tutor_tts_status()

  assert status.available is False
  assert status.provider == "none"
  assert status.fallback == "browser"


def test_synthesize_tutor_tts_uses_loaded_voice(monkeypatch, tmp_path) -> None:
  model_path = tmp_path / "voice.onnx"
  config_path = tmp_path / "voice.onnx.json"
  model_path.write_bytes(b"fake-model")
  config_path.write_text("{}", encoding="utf-8")

  class FakeVoice:
    def synthesize_wav(self, text, wav_file) -> None:
      wav_file.setnchannels(1)
      wav_file.setsampwidth(2)
      wav_file.setframerate(22050)
      wav_file.writeframes(b"\x00\x00" * 512)

  class FakePiperVoice:
    @staticmethod
    def load(model_path, config_path=None, use_cuda=False):
      assert model_path.endswith("voice.onnx")
      assert config_path and config_path.endswith("voice.onnx.json")
      assert use_cuda is False
      return FakeVoice()

  tutor_tts.clear_tutor_tts_cache()
  monkeypatch.setattr(tutor_tts, "PiperVoice", FakePiperVoice)
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_PROVIDER", "piper")
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_MODEL_PATH", str(model_path))
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_CONFIG_PATH", str(config_path))
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_VOICE", "de_DE-thorsten-medium")
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_MAX_CHARS", 280)

  audio_bytes, normalized_text = tutor_tts.synthesize_tutor_tts("Hallo\n  Tutor")

  assert normalized_text == "Hallo Tutor"
  assert audio_bytes[:4] == b"RIFF"
  tutor_tts.clear_tutor_tts_cache()


def test_persona_specific_tutor_tts_bundle_overrides_global_bundle(monkeypatch, tmp_path) -> None:
  global_model_path = tmp_path / "global.onnx"
  global_config_path = tmp_path / "global.onnx.json"
  persona_model_path = tmp_path / "coach.onnx"
  persona_config_path = tmp_path / "coach.onnx.json"
  global_model_path.write_bytes(b"global-model")
  global_config_path.write_text("{}", encoding="utf-8")
  persona_model_path.write_bytes(b"coach-model")
  persona_config_path.write_text("{}", encoding="utf-8")

  load_calls = []

  class FakeVoice:
    def synthesize_wav(self, text, wav_file) -> None:
      wav_file.setnchannels(1)
      wav_file.setsampwidth(2)
      wav_file.setframerate(22050)
      wav_file.writeframes(b"\x00\x00" * 256)

  class FakePiperVoice:
    @staticmethod
    def load(model_path, config_path=None, use_cuda=False):
      load_calls.append((model_path, config_path, use_cuda))
      return FakeVoice()

  tutor_tts.clear_tutor_tts_cache()
  monkeypatch.setattr(tutor_tts, "PiperVoice", FakePiperVoice)
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_PROVIDER", "piper")
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_MODEL_PATH", str(global_model_path))
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_CONFIG_PATH", str(global_config_path))
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_VOICE", "global-voice")
  monkeypatch.setenv("TUTOR_TTS_COACH_VOICE", "coach-voice")
  monkeypatch.setenv("TUTOR_TTS_COACH_MODEL_PATH", str(persona_model_path))
  monkeypatch.setenv("TUTOR_TTS_COACH_CONFIG_PATH", str(persona_config_path))

  status = tutor_tts.get_tutor_tts_status("coach")
  audio_bytes, normalized_text = tutor_tts.synthesize_tutor_tts("Hallo Coach", persona_key="coach")

  assert status.available is True
  assert status.voice_label == "coach-voice"
  assert status.voice_source == "persona:coach"
  assert normalized_text == "Hallo Coach"
  assert audio_bytes[:4] == b"RIFF"
  assert load_calls == [(str(persona_model_path), str(persona_config_path), False)]
  tutor_tts.clear_tutor_tts_cache()


def test_persona_specific_tutor_tts_bundle_falls_back_to_global_when_invalid(monkeypatch, tmp_path) -> None:
  global_model_path = tmp_path / "global.onnx"
  global_config_path = tmp_path / "global.onnx.json"
  global_model_path.write_bytes(b"global-model")
  global_config_path.write_text("{}", encoding="utf-8")

  load_calls = []

  class FakeVoice:
    def synthesize_wav(self, text, wav_file) -> None:
      wav_file.setnchannels(1)
      wav_file.setsampwidth(2)
      wav_file.setframerate(22050)
      wav_file.writeframes(b"\x00\x00" * 256)

  class FakePiperVoice:
    @staticmethod
    def load(model_path, config_path=None, use_cuda=False):
      load_calls.append((model_path, config_path, use_cuda))
      return FakeVoice()

  tutor_tts.clear_tutor_tts_cache()
  monkeypatch.setattr(tutor_tts, "PiperVoice", FakePiperVoice)
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_PROVIDER", "piper")
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_MODEL_PATH", str(global_model_path))
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_CONFIG_PATH", str(global_config_path))
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_VOICE", "global-voice")
  monkeypatch.setenv("TUTOR_TTS_COACH_VOICE", "coach-voice")
  monkeypatch.setenv("TUTOR_TTS_COACH_MODEL_PATH", str(tmp_path / "missing-coach.onnx"))
  monkeypatch.setenv("TUTOR_TTS_COACH_CONFIG_PATH", str(tmp_path / "missing-coach.onnx.json"))

  status = tutor_tts.get_tutor_tts_status("coach")
  audio_bytes, normalized_text = tutor_tts.synthesize_tutor_tts("Hallo Fallback", persona_key="coach")

  assert status.available is True
  assert status.voice_label == "global-voice"
  assert normalized_text == "Hallo Fallback"
  assert audio_bytes[:4] == b"RIFF"
  assert load_calls == [(str(global_model_path), str(global_config_path), False)]
  tutor_tts.clear_tutor_tts_cache()


def test_identity_specific_tutor_tts_bundle_accepts_woman_alias(monkeypatch, tmp_path) -> None:
  global_model_path = tmp_path / "global.onnx"
  global_config_path = tmp_path / "global.onnx.json"
  woman_model_path = tmp_path / "woman.onnx"
  woman_config_path = tmp_path / "woman.onnx.json"
  global_model_path.write_bytes(b"global-model")
  global_config_path.write_text("{}", encoding="utf-8")
  woman_model_path.write_bytes(b"woman-model")
  woman_config_path.write_text("{}", encoding="utf-8")

  load_calls = []

  class FakeVoice:
    def synthesize_wav(self, text, wav_file) -> None:
      wav_file.setnchannels(1)
      wav_file.setsampwidth(2)
      wav_file.setframerate(22050)
      wav_file.writeframes(b"\x00\x00" * 256)

  class FakePiperVoice:
    @staticmethod
    def load(model_path, config_path=None, use_cuda=False):
      load_calls.append((model_path, config_path, use_cuda))
      return FakeVoice()

  tutor_tts.clear_tutor_tts_cache()
  monkeypatch.setattr(tutor_tts, "PiperVoice", FakePiperVoice)
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_PROVIDER", "piper")
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_MODEL_PATH", str(global_model_path))
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_CONFIG_PATH", str(global_config_path))
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_VOICE", "global-voice")
  monkeypatch.setenv("TUTOR_TTS_WOMAN_VOICE", "woman-voice")
  monkeypatch.setenv("TUTOR_TTS_WOMAN_MODEL_PATH", str(woman_model_path))
  monkeypatch.setenv("TUTOR_TTS_WOMAN_CONFIG_PATH", str(woman_config_path))

  status = tutor_tts.get_tutor_tts_status("woman")
  audio_bytes, normalized_text = tutor_tts.synthesize_tutor_tts("Hallo Frau Tutor", persona_key="woman")

  assert status.available is True
  assert status.voice_label == "woman-voice"
  assert status.voice_source == "persona:woman"
  assert normalized_text == "Hallo Frau Tutor"
  assert audio_bytes[:4] == b"RIFF"
  assert load_calls == [(str(woman_model_path), str(woman_config_path), False)]
  tutor_tts.clear_tutor_tts_cache()


def test_identity_specific_tutor_tts_does_not_fall_back_to_global_for_woman(monkeypatch, tmp_path) -> None:
  global_model_path = tmp_path / "global.onnx"
  global_config_path = tmp_path / "global.onnx.json"
  global_model_path.write_bytes(b"global-model")
  global_config_path.write_text("{}", encoding="utf-8")

  tutor_tts.clear_tutor_tts_cache()
  monkeypatch.setattr(tutor_tts, "PiperVoice", object())
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_PROVIDER", "piper")
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_MODEL_PATH", str(global_model_path))
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_CONFIG_PATH", str(global_config_path))
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_VOICE", "global-male-voice")

  status = tutor_tts.get_tutor_tts_status("woman")
  bundle, bundle_error = tutor_tts._resolve_voice_bundle("woman")

  assert bundle is None
  assert status.available is False
  assert status.voice_label is None
  assert "selected tutor identity" in status.detail.lower()
  assert "selected tutor identity" in bundle_error.lower()
  tutor_tts.clear_tutor_tts_cache()


def test_identity_specific_tutor_tts_does_not_fall_back_to_global_for_man(monkeypatch, tmp_path) -> None:
  global_model_path = tmp_path / "global.onnx"
  global_config_path = tmp_path / "global.onnx.json"
  global_model_path.write_bytes(b"global-model")
  global_config_path.write_text("{}", encoding="utf-8")

  tutor_tts.clear_tutor_tts_cache()
  monkeypatch.setattr(tutor_tts, "PiperVoice", object())
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_PROVIDER", "piper")
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_MODEL_PATH", str(global_model_path))
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_CONFIG_PATH", str(global_config_path))
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_VOICE", "global-male-voice")

  status = tutor_tts.get_tutor_tts_status("man")
  bundle, bundle_error = tutor_tts._resolve_voice_bundle("man")

  assert bundle is None
  assert status.available is False
  assert status.voice_label is None
  assert "selected tutor identity" in status.detail.lower()
  assert "selected tutor identity" in bundle_error.lower()
  tutor_tts.clear_tutor_tts_cache()


def test_identity_specific_tutor_tts_bundle_falls_back_to_legacy_coach_bundle_for_man(monkeypatch, tmp_path) -> None:
  global_model_path = tmp_path / "global.onnx"
  global_config_path = tmp_path / "global.onnx.json"
  coach_model_path = tmp_path / "coach.onnx"
  coach_config_path = tmp_path / "coach.onnx.json"
  global_model_path.write_bytes(b"global-model")
  global_config_path.write_text("{}", encoding="utf-8")
  coach_model_path.write_bytes(b"coach-model")
  coach_config_path.write_text("{}", encoding="utf-8")

  load_calls = []

  class FakeVoice:
    def synthesize_wav(self, text, wav_file) -> None:
      wav_file.setnchannels(1)
      wav_file.setsampwidth(2)
      wav_file.setframerate(22050)
      wav_file.writeframes(b"\x00\x00" * 256)

  class FakePiperVoice:
    @staticmethod
    def load(model_path, config_path=None, use_cuda=False):
      load_calls.append((model_path, config_path, use_cuda))
      return FakeVoice()

  tutor_tts.clear_tutor_tts_cache()
  monkeypatch.setattr(tutor_tts, "PiperVoice", FakePiperVoice)
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_PROVIDER", "piper")
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_MODEL_PATH", str(global_model_path))
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_CONFIG_PATH", str(global_config_path))
  monkeypatch.setattr(tutor_tts, "TUTOR_TTS_VOICE", "global-voice")
  monkeypatch.setenv("TUTOR_TTS_COACH_VOICE", "coach-voice")
  monkeypatch.setenv("TUTOR_TTS_COACH_MODEL_PATH", str(coach_model_path))
  monkeypatch.setenv("TUTOR_TTS_COACH_CONFIG_PATH", str(coach_config_path))

  status = tutor_tts.get_tutor_tts_status("man")
  audio_bytes, normalized_text = tutor_tts.synthesize_tutor_tts("Hallo Mann Tutor", persona_key="man")

  assert status.available is True
  assert status.voice_label == "coach-voice"
  assert normalized_text == "Hallo Mann Tutor"
  assert audio_bytes[:4] == b"RIFF"
  assert load_calls == [(str(coach_model_path), str(coach_config_path), False)]
  tutor_tts.clear_tutor_tts_cache()


def test_tutor_tts_endpoint_returns_503_when_local_provider_is_unavailable(monkeypatch) -> None:
  client = TestClient(main.app)
  monkeypatch.setattr(
    main,
    "get_tutor_tts_status",
    lambda persona_key=None: TutorTtsStatus(
      available=False,
      provider="none",
      fallback="browser",
      voice_label="de_DE-thorsten-medium",
      detail="Local Tutor TTS is disabled.",
    ),
  )

  response = client.post("/api/tutor/tts", json={"text": "Hallo Tutor"})

  assert response.status_code == 503
  assert "disabled" in response.json()["detail"].lower()


def test_tutor_tts_endpoint_returns_audio_and_headers(monkeypatch) -> None:
  client = TestClient(main.app)
  captured = {}
  monkeypatch.setattr(
    main,
    "get_tutor_tts_status",
    lambda persona_key=None: TutorTtsStatus(
      available=True,
      provider="local",
      fallback="browser",
      voice_label="coach-voice",
      voice_source="persona:coach",
      detail="Local Tutor TTS is ready.",
    ),
  )
  monkeypatch.setattr(
    main,
    "synthesize_tutor_tts",
    lambda text, persona_key=None: (
      captured.setdefault("persona_key", persona_key),
      (_build_wav_bytes(), str(text).strip()),
    )[1],
  )

  response = client.post(
    "/api/tutor/tts",
    json={"text": "Guten Tag", "turn_id": "turn-1", "sentence_index": 1, "persona_key": "coach"},
  )

  assert response.status_code == 200
  assert response.headers["content-type"].startswith("audio/wav")
  assert response.headers["x-tutor-tts-provider"] == "local"
  assert response.headers["x-tutor-tts-voice"] == "coach-voice"
  assert response.headers["x-tutor-tts-voice-source"] == "persona:coach"
  assert captured["persona_key"] == "coach"
  assert response.content[:4] == b"RIFF"


def test_frontend_wires_local_tutor_tts_runtime_and_fallback_controls() -> None:
  runtime = Path("static/assets/tutor-runtime.js").read_text(encoding="utf-8")
  frontend = Path("static/assets/app-features.js").read_text(encoding="utf-8")
  tts_endpoint = "/api/tutor/tts"

  assert 'window.tutorAudioSupported = function tutorAudioSupported()' in runtime
  assert 'window.stopTutorAudio = function stopTutorAudio(options = {})' in runtime
  assert 'window.playTutorReplyAudio = function playTutorReplyAudio(text, options = {})' in runtime
  assert 'if (type === "sentence") {' in runtime
  assert 'queueTutorSpeechChunks(audioRuntime, [sentenceText]);' in runtime
  assert tts_endpoint in runtime
  assert 'const outgoingPersonaKey = runtime.personaKey || window.getTutorVoicePersonaKey?.() || state.tutorAvatar;' in runtime
  assert 'persona_key: outgoingPersonaKey' in runtime
  assert 'window.chatBrowserSpeechSupported = function chatBrowserSpeechSupported()' in frontend
  assert 'window.playTutorReplyAudio(state.chatLastAssistantReply, { source: "replay" });' in frontend
  assert 'window.playTutorReplyAudio(data.reply, { turnId, source: "blocking" });' in frontend
  assert 'window.getTutorConversationPersonaKey = function getTutorConversationPersonaKey()' in frontend
  assert 'window.getTutorVoicePersonaKey = function getTutorVoicePersonaKey()' in frontend
  assert 'const transcriptPersonaKey = String(data?.persona_key || "").trim().toLowerCase();' in frontend
  assert 'state.tutorAvatar = transcriptPersonaKey;' not in frontend
