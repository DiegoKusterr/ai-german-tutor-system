from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

from ..schemas import MockMediaSegment

BASE_DIR = Path(__file__).resolve().parents[2]
APP_DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(BASE_DIR / "data"))).resolve()
MOCK_AUDIO_DIR = APP_DATA_DIR / "mock_exam_audio"
MOCK_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def get_mock_audio_provider_preference() -> str:
    raw = os.getenv("MOCK_AUDIO_PROVIDER", "none").strip().lower()
    valid = {"auto", "local", "none"}
    return raw if raw in valid else "local"


def get_mock_audio_voice_hint() -> str:
    return os.getenv("MOCK_AUDIO_VOICE_HINT", "").strip()


def get_mock_audio_voice_gender() -> Literal["female", "male", "auto"]:
    raw = os.getenv("MOCK_AUDIO_VOICE_GENDER", "auto").strip().lower()
    if raw in {"female", "male"}:
        return raw
    return "auto"


def eager_mock_audio_generation_enabled() -> bool:
    return os.getenv("MOCK_AUDIO_EAGER", "0").strip().lower() in {"1", "true", "yes", "on"}


def _powershell_executable() -> str | None:
    if os.name != "nt":
        return None
    return shutil.which("powershell") or shutil.which("pwsh")


def local_mock_audio_available() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return _powershell_executable() is not None


def resolve_mock_audio_provider() -> Literal["local", "none"]:
    provider = get_mock_audio_provider_preference()
    if provider == "none":
        return "none"
    if provider in {"auto", "local"} and local_mock_audio_available():
        return "local"
    return "none"


def _shell_quote(value: str) -> str:
    return value.replace("'", "''")


def _windows_tts_rate(playback_rate: float) -> int:
    # System.Speech uses a coarse range from -10 to 10. Keep the mock close to the exam pace.
    raw = round((float(playback_rate) - 1.0) * 12)
    return max(-4, min(2, raw))


def _normalize_voice_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()


def _voice_rank(name: str, hint: str, gender: Literal["female", "male", "auto"]) -> int:
    normalized = _normalize_voice_name(name)
    score = 0
    if hint:
        normalized_hint = _normalize_voice_name(hint)
        if normalized == normalized_hint:
            score += 100
        elif normalized_hint and normalized_hint in normalized:
            score += 55
    female_hints = {"female", "frau", "weiblich", "hedda", "katja", "helena", "vicki", "anna", "petra", "sandra"}
    male_hints = {"male", "mann", "maennlich", "stefan", "thomas", "markus", "ralf", "daniel", "andreas", "jonas"}
    voice_tokens = set(normalized.split())
    if gender == "female":
        if voice_tokens & female_hints:
            score += 18
        if voice_tokens & male_hints:
            score -= 8
    elif gender == "male":
        if voice_tokens & male_hints:
            score += 18
        if voice_tokens & female_hints:
            score -= 8
    if "deutsch" in voice_tokens or "german" in voice_tokens:
        score += 6
    if "desktop" in voice_tokens:
        score += 2
    return score


def choose_mock_audio_voice_name(voices: list[str], *, hint: str | None = None, gender: Literal["female", "male", "auto"] = "auto") -> str | None:
    if not voices:
        return None
    resolved_hint = str(hint or get_mock_audio_voice_hint()).strip()
    resolved_gender = gender if gender in {"female", "male"} else get_mock_audio_voice_gender()
    ranked = sorted(voices, key=lambda item: (_voice_rank(item, resolved_hint, resolved_gender), item.lower()), reverse=True)
    return ranked[0] if ranked else voices[0]


def _audio_cache_key(
    segment: MockMediaSegment,
    *,
    voice_hint: str,
    voice_gender: Literal["female", "male", "auto"],
) -> str:
    raw = "|".join(
        [
            str(segment.module),
            str(segment.part_key),
            str(segment.source_title),
            str(segment.script_text),
            str(segment.audio_plays),
            str(segment.playback_rate),
            str(voice_hint),
            str(voice_gender),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _audio_path(audio_key: str) -> Path:
    return MOCK_AUDIO_DIR / f"{audio_key}.wav"


def _audio_manifest_path(audio_key: str) -> Path:
    return MOCK_AUDIO_DIR / f"{audio_key}.json"


def _write_audio_manifest(
    audio_key: str,
    *,
    segment: MockMediaSegment,
    voice_hint: str,
    voice_gender: Literal["female", "male", "auto"],
) -> None:
    payload = {
        "script_text": segment.script_text,
        "playback_rate": segment.playback_rate,
        "voice_hint": voice_hint,
        "voice_gender": voice_gender,
    }
    _audio_manifest_path(audio_key).write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def _read_audio_manifest(audio_key: str) -> dict[str, str | float] | None:
    path = _audio_manifest_path(audio_key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _synthesize_windows_mock_audio(
    *,
    script_text: str,
    output_path: Path,
    playback_rate: float,
    voice_hint: str,
    voice_gender: Literal["female", "male", "auto"],
) -> str | None:
    executable = _powershell_executable()
    if not executable:
        raise RuntimeError("No local PowerShell runtime found for mock audio synthesis.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    voice_label: str | None = None
    tmp_text_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as tmp_text:
            tmp_text.write(script_text)
            tmp_text_path = Path(tmp_text.name)

        command = """
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$text = Get-Content -Raw -Encoding UTF8 '{text_path}'
$output = '{output_path}'
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices = $synth.GetInstalledVoices() | Where-Object {{ $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'de-*' }}
$voiceHint = '{voice_hint}'
$genderPreference = '{voice_gender}'
$voice = $null
if ($voiceHint) {{
  $voice = $voices | Where-Object {{ $_.VoiceInfo.Name -like "*$voiceHint*" }} | Select-Object -First 1
}}
if (-not $voice -and $genderPreference -ne 'auto') {{
  $voice = $voices | Where-Object {{ $_.VoiceInfo.Gender.ToString().ToLowerInvariant() -eq $genderPreference }} | Select-Object -First 1
}}
if (-not $voice) {{
  $voice = $voices | Select-Object -First 1
}}
if ($voice) {{
  $synth.SelectVoice($voice.VoiceInfo.Name)
  $voiceLabel = $voice.VoiceInfo.Name
}} else {{
  $voiceLabel = $synth.Voice.Name
}}
$synth.Rate = {tts_rate}
$synth.SetOutputToWaveFile($output)
$synth.Speak($text)
$synth.SetOutputToDefaultAudioDevice()
$synth.Dispose()
Write-Output $voiceLabel
        """.strip().format(
            text_path=_shell_quote(str(tmp_text_path)),
            output_path=_shell_quote(str(output_path)),
            voice_hint=_shell_quote(voice_hint),
            voice_gender=_shell_quote(voice_gender),
            tts_rate=_windows_tts_rate(playback_rate),
        )

        result = subprocess.run(
            [executable, "-NoProfile", "-NonInteractive", "-Command", command],
            check=True,
            capture_output=True,
            text=True,
            timeout=45,
        )
        voice_label = (result.stdout or "").strip() or None
    except subprocess.CalledProcessError as exc:  # pragma: no cover - depends on host voice stack
        message = (exc.stderr or exc.stdout or "").strip() or "Unknown local TTS failure."
        raise RuntimeError(f"Windows mock audio synthesis failed: {message}") from exc
    finally:
        if tmp_text_path and tmp_text_path.exists():
            try:
                tmp_text_path.unlink()
            except OSError:
                pass

    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError("Windows mock audio synthesis did not create a playable WAV file.")
    return voice_label


def ensure_mock_audio_segment(
    segment: MockMediaSegment,
    *,
    voice_gender_override: Literal["female", "male", "auto"] | None = None,
) -> MockMediaSegment:
    provider = resolve_mock_audio_provider()
    if provider == "none":
        return segment.model_copy(update={"audio_provider": "none"})

    voice_hint = get_mock_audio_voice_hint()
    voice_gender = voice_gender_override if voice_gender_override in {"female", "male", "auto"} else get_mock_audio_voice_gender()
    audio_key = _audio_cache_key(segment, voice_hint=voice_hint, voice_gender=voice_gender)
    output_path = _audio_path(audio_key)
    voice_label = "Windows System.Speech"
    _write_audio_manifest(audio_key, segment=segment, voice_hint=voice_hint, voice_gender=voice_gender)
    if eager_mock_audio_generation_enabled() and (not output_path.exists() or output_path.stat().st_size <= 0):
        voice_label = _synthesize_windows_mock_audio(
            script_text=segment.script_text,
            output_path=output_path,
            playback_rate=segment.playback_rate,
            voice_hint=voice_hint,
            voice_gender=voice_gender,
        ) or voice_label
    return segment.model_copy(
        update={
            "audio_key": audio_key,
            "audio_url": f"/api/exam/mock-media/{audio_key}",
            "audio_provider": "local_windows_tts",
            "voice_label": voice_label,
        }
    )


def get_mock_audio_file(audio_key: str) -> tuple[Path, str, str]:
    if not re.fullmatch(r"[a-f0-9]{16,64}", str(audio_key or "")):
        raise ValueError("Invalid mock audio key.")
    path = _audio_path(audio_key)
    if (not path.exists() or path.stat().st_size <= 0) and resolve_mock_audio_provider() == "local":
        manifest = _read_audio_manifest(audio_key)
        if manifest:
            _synthesize_windows_mock_audio(
                script_text=str(manifest.get("script_text", "")),
                output_path=path,
                playback_rate=float(manifest.get("playback_rate", 1.0) or 1.0),
                voice_hint=str(manifest.get("voice_hint", "")),
                voice_gender=str(manifest.get("voice_gender", "auto")),  # type: ignore[arg-type]
            )
    if not path.exists() or path.stat().st_size <= 0:
        raise FileNotFoundError("Mock audio file not found.")
    return path, "audio/wav", f"goethe-mock-{audio_key}.wav"
