import json
import asyncio
import mimetypes
import os
import logging
import random
import re
import socket
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread, Timer
from time import perf_counter
from typing import Any, Literal, TypedDict, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen
from uuid import uuid4
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request as FastAPIRequest, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from local_https import LOCAL_CA_CERT_PATH
from learning_app.db import init_db as init_learning_db
from learning_app.router import router as learning_router
from learning_app.schemas import (
    ApiChatRequest,
    ApiChatResponse,
    ChatEditMessageRequest,
    ChatRestoreMessageRequest,
    TutorStreamRequest,
)
from learning_app.services.common import detect_generic_errors, ensure_local_user
from learning_app.services.tutor_tts import get_tutor_tts_status, synthesize_tutor_tts

try:
    from faster_whisper import WhisperModel
except Exception:  # pragma: no cover - optional local STT dependency
    WhisperModel = None


load_dotenv()
logger = logging.getLogger("german_speaking_coach")
mimetypes.add_type("image/webp", ".webp")

BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "static" / "index.html"
DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(BASE_DIR / "data"))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "state.json"

DEFAULT_LEVEL = "B2"
TRANSCRIBE_PROVIDER = os.getenv("TRANSCRIBE_PROVIDER", "local").strip().lower()
LOCAL_TRANSCRIBE_MODEL = os.getenv("LOCAL_TRANSCRIBE_MODEL", "base").strip() or "base"
LOCAL_TRANSCRIBE_DEVICE = os.getenv("LOCAL_TRANSCRIBE_DEVICE", "cpu").strip().lower() or "cpu"
if LOCAL_TRANSCRIBE_DEVICE not in {"cpu", "cuda", "auto"}:
    LOCAL_TRANSCRIBE_DEVICE = "cpu"
LOCAL_TRANSCRIBE_COMPUTE_TYPE = (
    os.getenv("LOCAL_TRANSCRIBE_COMPUTE_TYPE", "int8").strip().lower() or "int8"
)
try:
    LOCAL_TRANSCRIBE_BEAM_SIZE = int(os.getenv("LOCAL_TRANSCRIBE_BEAM_SIZE", "1").strip())
except ValueError:
    LOCAL_TRANSCRIBE_BEAM_SIZE = 1
LOCAL_TRANSCRIBE_BEAM_SIZE = max(1, min(LOCAL_TRANSCRIBE_BEAM_SIZE, 5))
LOCAL_TRANSCRIBE_VAD_FILTER = os.getenv("LOCAL_TRANSCRIBE_VAD_FILTER", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
    "si",
    "sí",
}
ALLOW_RULEBASED_FALLBACK = os.getenv("ALLOW_RULEBASED_FALLBACK", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
    "si",
    "sí",
}
try:
    OLLAMA_REQUEST_TIMEOUT = int(os.getenv("OLLAMA_REQUEST_TIMEOUT", "120").strip())
except ValueError:
    OLLAMA_REQUEST_TIMEOUT = 120
OLLAMA_REQUEST_TIMEOUT = max(60, OLLAMA_REQUEST_TIMEOUT)
try:
    OLLAMA_CHAT_TIMEOUT = int(os.getenv("OLLAMA_CHAT_TIMEOUT", "35").strip())
except ValueError:
    OLLAMA_CHAT_TIMEOUT = 35
OLLAMA_CHAT_TIMEOUT = max(8, min(OLLAMA_CHAT_TIMEOUT, OLLAMA_REQUEST_TIMEOUT))
TUTOR_STREAMING_ENABLED = os.getenv("TUTOR_STREAMING_ENABLED", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
    "si",
    "sí",
}

OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m").strip() or "30m"
OLLAMA_ENABLE_STARTUP_WARMUP = os.getenv("OLLAMA_ENABLE_STARTUP_WARMUP", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
    "si",
    "sí",
}
try:
    OLLAMA_STARTUP_WARMUP_DELAY_SEC = float(os.getenv("OLLAMA_STARTUP_WARMUP_DELAY_SEC", "8").strip())
except ValueError:
    OLLAMA_STARTUP_WARMUP_DELAY_SEC = 8.0
OLLAMA_STARTUP_WARMUP_DELAY_SEC = max(0.0, min(OLLAMA_STARTUP_WARMUP_DELAY_SEC, 60.0))
try:
    OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.35").strip())
except ValueError:
    OLLAMA_TEMPERATURE = 0.35
try:
    OLLAMA_TOP_P = float(os.getenv("OLLAMA_TOP_P", "0.9").strip())
except ValueError:
    OLLAMA_TOP_P = 0.9
try:
    OLLAMA_REPEAT_PENALTY = float(os.getenv("OLLAMA_REPEAT_PENALTY", "1.07").strip())
except ValueError:
    OLLAMA_REPEAT_PENALTY = 1.07
try:
    OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "2048").strip())
except ValueError:
    OLLAMA_NUM_CTX = 2048
try:
    OLLAMA_CHAT_MAX_TOKENS = int(os.getenv("OLLAMA_CHAT_MAX_TOKENS", "72").strip())
except ValueError:
    OLLAMA_CHAT_MAX_TOKENS = 72
OLLAMA_CHAT_MAX_TOKENS = max(40, min(OLLAMA_CHAT_MAX_TOKENS, 256))
try:
    OLLAMA_FEEDBACK_MAX_TOKENS = int(os.getenv("OLLAMA_FEEDBACK_MAX_TOKENS", "700").strip())
except ValueError:
    OLLAMA_FEEDBACK_MAX_TOKENS = 700
OLLAMA_FEEDBACK_MAX_TOKENS = max(300, min(OLLAMA_FEEDBACK_MAX_TOKENS, 1800))
try:
    OLLAMA_NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", "0").strip())
except ValueError:
    OLLAMA_NUM_THREAD = 0
if OLLAMA_NUM_THREAD <= 0:
    cpu_count = os.cpu_count() or 4
    OLLAMA_NUM_THREAD = max(2, cpu_count - 1)
try:
    OLLAMA_MAX_HISTORY_MESSAGES = int(os.getenv("OLLAMA_MAX_HISTORY_MESSAGES", "6").strip())
except ValueError:
    OLLAMA_MAX_HISTORY_MESSAGES = 6
OLLAMA_MAX_HISTORY_MESSAGES = max(4, min(OLLAMA_MAX_HISTORY_MESSAGES, 40))
try:
    CHAT_HISTORY_CHAR_BUDGET = int(os.getenv("CHAT_HISTORY_CHAR_BUDGET", "2400").strip())
except ValueError:
    CHAT_HISTORY_CHAR_BUDGET = 2400
CHAT_HISTORY_CHAR_BUDGET = max(500, min(CHAT_HISTORY_CHAR_BUDGET, 12000))
try:
    CHAT_REPLY_MAX_WORDS = int(os.getenv("CHAT_REPLY_MAX_WORDS", "55").strip())
except ValueError:
    CHAT_REPLY_MAX_WORDS = 55
CHAT_REPLY_MAX_WORDS = max(18, min(CHAT_REPLY_MAX_WORDS, 120))
try:
    OLLAMA_RUNTIME_CACHE_TTL_SEC = float(os.getenv("OLLAMA_RUNTIME_CACHE_TTL_SEC", "8").strip())
except ValueError:
    OLLAMA_RUNTIME_CACHE_TTL_SEC = 8.0
OLLAMA_RUNTIME_CACHE_TTL_SEC = max(0.0, min(OLLAMA_RUNTIME_CACHE_TTL_SEC, 60.0))
try:
    OLLAMA_FAST_TURN_USER_THRESHOLD = int(os.getenv("OLLAMA_FAST_TURN_USER_THRESHOLD", "2").strip())
except ValueError:
    OLLAMA_FAST_TURN_USER_THRESHOLD = 2
OLLAMA_FAST_TURN_USER_THRESHOLD = max(1, min(OLLAMA_FAST_TURN_USER_THRESHOLD, 6))
try:
    OLLAMA_FAST_MESSAGE_CHAR_THRESHOLD = int(os.getenv("OLLAMA_FAST_MESSAGE_CHAR_THRESHOLD", "160").strip())
except ValueError:
    OLLAMA_FAST_MESSAGE_CHAR_THRESHOLD = 160
OLLAMA_FAST_MESSAGE_CHAR_THRESHOLD = max(60, min(OLLAMA_FAST_MESSAGE_CHAR_THRESHOLD, 500))
try:
    STATE_PERSIST_DEBOUNCE_MS = int(os.getenv("STATE_PERSIST_DEBOUNCE_MS", "1200").strip())
except ValueError:
    STATE_PERSIST_DEBOUNCE_MS = 1200
STATE_PERSIST_DEBOUNCE_MS = max(0, min(STATE_PERSIST_DEBOUNCE_MS, 10000))
try:
    FRONTEND_CHAT_TIMEOUT_MS = int(os.getenv("FRONTEND_CHAT_TIMEOUT_MS", "45000").strip())
except ValueError:
    FRONTEND_CHAT_TIMEOUT_MS = 45000
FRONTEND_CHAT_TIMEOUT_MS = max(12000, min(FRONTEND_CHAT_TIMEOUT_MS, 120000))
try:
    FRONTEND_TRANSCRIBE_TIMEOUT_MS = int(os.getenv("FRONTEND_TRANSCRIBE_TIMEOUT_MS", "50000").strip())
except ValueError:
    FRONTEND_TRANSCRIBE_TIMEOUT_MS = 50000
FRONTEND_TRANSCRIBE_TIMEOUT_MS = max(12000, min(FRONTEND_TRANSCRIBE_TIMEOUT_MS, 120000))

TRANSCRIBE_PROMPT = (
    "German conversation transcript with natural punctuation and capitalization. "
    "Use umlauts (ä, ö, ü) and ß when appropriate."
)

CHAT_PROVIDER = os.getenv("CHAT_PROVIDER", "ollama").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_SPEED_PRESET = os.getenv("OLLAMA_SPEED_PRESET", "balanced").strip().lower()
if OLLAMA_SPEED_PRESET not in {"turbo", "balanced", "quality"}:
    OLLAMA_SPEED_PRESET = "balanced"
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
OLLAMA_ACTIVE_MODEL = OLLAMA_MODEL
OLLAMA_MODEL_PICK_LOCK = Lock()
OLLAMA_RUNTIME_CACHE_LOCK = Lock()
OLLAMA_CACHE_MISS = object()
OLLAMA_RUNTIME_CACHE: dict[str, dict[str, Any]] = {
    "tags_payload": {"expires_at": 0.0, "value": OLLAMA_CACHE_MISS},
}
LOCAL_TRANSCRIBE_LOCK = Lock()
LOCAL_TRANSCRIBE_INSTANCE: Any | None = None
LOCAL_TRANSCRIBE_INSTANCE_KEY = ""
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Europe/Madrid").strip() or "Europe/Madrid"

SYSTEM_PROMPT = """<role>
Du bist ein echter deutscher Gespraechspartner fuer freies Sprechtraining.
Zielniveau: {level} (GER/CEFR).
</role>

<regeln>
1) Open-Domain: antworte sinnvoll zu jedem Thema.
2) Antworte immer direkt auf die letzte Nutzerfrage.
3) Wenn mehrere Fragen gestellt werden, beantworte alle kurz.
4) Keine Lob-Einstiege oder Floskeln wie "Das ist ein guter Punkt" oder "Gute Frage".
5) Maximal eine kurze Rueckfrage, nur wenn sie wirklich hilft.
6) Sprache: korrektes Deutsch mit Grossschreibung, Zeichensetzung, Umlauten und ß.
7) Stil: natuerlich, direkt und gesprochennah, 1-3 Saetze, keine Listen, kein Meta-Talk, keine Vorrede.
8) Niveau:
   - A1/A2: einfache Woerter, kurze Saetze.
   - B1/B2: alltagsnah und variabel.
   - C1/C2: praezise und idiomatisch.
9) Keine Mini-Korrektur oder Grammatikerklaerung im Haupttext, ausser der Nutzer verlangt sie explizit.
10) Datum/Uhrzeit/Wochentag nur aus der bereitgestellten Laufzeit-Info.
</regeln>
"""

CHAT_RESPONSE_SYSTEM_NOTE = (
    f"Standard: antworte direkt in hoechstens 2 kurzen Saetzen und hoechstens {CHAT_REPLY_MAX_WORDS} Woertern. "
    "Keine Listen, kein Meta-Talk, keine Wiederholungen, keine Lob-Einstiege."
)

CHAT_SPOKEN_RESPONSE_SYSTEM_NOTE = (
    "Formuliere so, wie man es laut sagen wuerde: kurze, fluessige Saetze, "
    "natuerliche Uebergaenge, keine Klammern, keine Aufzaehlungen, keine Vorrede."
)

FINAL_FEEDBACK_PROMPT = """Vas a analizar una conversacion de practica oral de aleman.
El nivel objetivo del alumno es {level}.

Necesito un informe en espanol, claro y accionable, con estas secciones y este orden:
1) Resumen de rendimiento (5-8 lineas).
2) Errores detectados (lista numerada):
   - Error original del alumno.
   - Correccion natural en aleman.
   - Explicacion corta.
3) Pronunciacion y fluidez:
   - Palabras o frases clave que deberia pronunciar mejor.
   - Guia aproximada para hispanohablante.
   - Recomendaciones concretas para sonar mas natural.
4) Que repasar (plan corto):
   - 5 puntos de estudio priorizados.
   - 5 frases de practica alineadas con sus errores.

Usa ejemplos del transcript.

Transcript:
{transcript}
"""

MONOLOGUE_FEEDBACK_PROMPT = """Vas a analizar un monologo oral en aleman.
Nivel actual declarado por el alumno: {level}
Nivel objetivo (goal): {goal_level}
Nivel estimado inicial por heuristica: {estimated_level}

Devuelve SIEMPRE en espanol, con ejemplos en aleman, y en este orden exacto.
MUY IMPORTANTE: no minimices errores. Debes detectar y corregir puntuacion, comas, finales de frase,
inicios de frase, interrogaciones/exclamaciones, gramatica, orden verbal, conectores, vocabulario,
expresiones poco naturales y articulos/casos cuando aplique.

Si el texto viene casi sin puntuacion, tomalo como error claro y muestra como quedaria correctamente.

Formato exacto:
1) Diagnostico breve (nivel estimado real y por que).
2) Errores clave (lista numerada, minimo 8 si el texto es largo):
   - Categoria (Puntuacion / Gramatica / Orden verbal / Vocabulario / Expresion / Fluidez)
   - Frase original
   - Correccion natural
   - Explicacion corta
3) Version mejorada del monologo (alemán natural, 120-180 palabras).
4) Pronunciacion y fluidez:
   - 6 palabras/frases criticas
   - Guia breve para hispanohablante
5) Brecha hasta el nivel objetivo:
   - Que te falta para llegar de {estimated_level} a {goal_level}
6) Plan de estudio accionable (2 semanas):
   - prioridades
   - ejercicios concretos diarios (20-30 min)
   - checklist final de progreso

Texto original del alumno (sin corregir):
{raw_monologue}

Version auto-segmentada (heuristica, puede contener errores):
{normalized_monologue}

Observaciones heuristicas iniciales:
{heuristic_notes}
"""

GOETHE_OPEN_EVAL_PROMPT = """<role>
Du bist ein strenger, aber hilfreicher Goethe-Pruefer und Sprachcoach.
Ziel: Der Lernende besteht die Goethe-Pruefung auf Niveau {level}.
</role>

<mission>
Trainiere exakt pruefungsrelevant (Goethe-Formate), korrigiere praezise und priorisiere Fehler, die Punkte kosten.
</mission>

<rules>
1) Antworte zuerst auf die Aufgabe, nicht allgemein.
2) Nutze nur natuerliches Deutsch auf Niveau {level}; Erklaerungen auf Spanisch.
3) Fuer jede Antwort des Lernenden:
   - Gib Punktzahl (0-{max_points})
   - Nenne 1 Staerke
   - Nenne 2-4 kritische Fehler (Grammatik, Wortstellung, Kasus, Kollokation, Register, Koharenz)
   - Gib eine korrigierte Musterantwort in natuerlichem Deutsch
4) Bei Sprechen/Schreiben: bewerte nach Aufgabenbezug, Koharenz/Kohasion, Sprachrichtigkeit, Wortschatz/Angemessenheit.
5) Keine Floskeln, keine irrelevanten Rueckfragen, kein "als KI...".
6) Kurz, klar, umsetzbar.
</rules>

<exam_focus>
Goethe-Module: Lesen, Horen, Schreiben, Sprechen.
Ergaenzend: Grammatik, Wortschatz, Verben nur wenn pruefungsrelevant.
</exam_focus>

<task_data>
Modul: {module_label}
Aufgabe: {question_prompt}
Palabras clave recomendadas: {keywords_text}
Respuesta del alumno: {user_answer}
</task_data>

Devuelve SOLO JSON valido (sin markdown) con esta forma exacta:
{{
  "score": entero,
  "strength": "string",
  "critical_errors": ["string", "string"],
  "corrected_answer_de": "string",
  "next_step": "string"
}}
"""

LEVEL_PATTERN = r"^(A1|A2|B1|B2|C1|C2)$"
ExamName = Literal["goethe", "telc", "testdaf"]
ExamSection = Literal["sprechen", "hoeren", "lesen", "schreiben", "grammatik", "wortschatz", "verben"]
TranscriptRole = Literal["user", "assistant"]
TranscriptStatus = Literal["active", "superseded", "outdated"]
TutorPersonaKey = Literal["studio", "coach", "examiner"]


class TranscriptEntryMetaDict(TypedDict, total=False):
    source: str


class TranscriptEntryDict(TypedDict, total=False):
    id: str
    role: TranscriptRole
    text: str
    timestamp: str
    created_at: str
    status: TranscriptStatus
    reply_to_id: str | None
    version_group_id: str
    version_index: int
    edited_from_id: str | None
    invalidated_by_id: str | None
    meta: TranscriptEntryMetaDict


class SessionState(TypedDict, total=False):
    level: str
    started_at: str
    transcript: list[TranscriptEntryDict]
    next_version_group_index: int
    coherence: "SessionCoherenceDict"


class SessionCoherenceDict(TypedDict, total=False):
    persona_key: TutorPersonaKey
    assistant_facts: dict[str, str]
    conversation_facts: dict[str, str]
    last_rebuilt_at: str


class LearnerProfile(TypedDict):
    topic_counts: dict[str, int]
    common_corrections: dict[str, int]
    total_user_messages: int
    last_updated: str


class GeneratedQuestionDict(TypedDict):
    id: str
    type: Literal["mcq", "cloze", "short", "open"]
    prompt: str
    support_text: str | None
    options: list[str]
    answer: str
    explanation: str
    max_points: int
    keywords: list[str]
    min_words: int


SESSIONS: dict[str, SessionState] = {}
SESSIONS_LOCK = Lock()
PROFILE_LOCK = Lock()
STATE_PERSIST_LOCK = Lock()
STATE_PERSIST_TIMER: Timer | None = None
STATE_PERSIST_DIRTY = False
OLLAMA_WARMUP_LOCK = Lock()
OLLAMA_WARMED = False
OLLAMA_TURBO_INSTALL_LOCK = Lock()
OLLAMA_TURBO_INSTALL_STATE = {
    "running": False,
    "installed": False,
    "detail": "",
    "target_model": OLLAMA_PULL_FAST_MODEL,
}
LEARNER_PROFILE: LearnerProfile = {
    "topic_counts": {},
    "common_corrections": {},
    "total_user_messages": 0,
    "last_updated": datetime.now(timezone.utc).isoformat(),
}
EXAM_MOCKS: dict[str, dict[str, Any]] = {}
EXAM_MOCKS_LOCK = Lock()
EXERCISE_SETS: dict[str, dict[str, Any]] = {}
EXERCISE_SETS_LOCK = Lock()
FLASHCARD_SETS: dict[str, dict[str, Any]] = {}
FLASHCARD_SETS_LOCK = Lock()

DEFAULT_TUTOR_PERSONA: TutorPersonaKey = "studio"
TUTOR_PERSONA_REGISTRY: dict[TutorPersonaKey, dict[str, str]] = {
    "studio": {
        "persona_title": "Studio tutor",
        "identity_summary": "Ich bin dein digitaler Deutsch-Tutor.",
        "origin_summary": "Ich bin digital und habe keinen festen Wohnort.",
        "age_summary": "Ich habe kein echtes biologisches Alter.",
        "tone_summary": "ruhig, klar und freundlich-professionell",
    },
    "coach": {
        "persona_title": "Coach",
        "identity_summary": "Ich bin dein digitaler Deutsch-Coach.",
        "origin_summary": "Ich bin digital und habe keinen festen Wohnort.",
        "age_summary": "Ich habe kein echtes biologisches Alter.",
        "tone_summary": "ermutigend, direkt und alltagsnah",
    },
    "examiner": {
        "persona_title": "Examiner",
        "identity_summary": "Ich bin dein digitaler Pruefungs-Tutor.",
        "origin_summary": "Ich bin digital und habe keinen festen Wohnort.",
        "age_summary": "Ich habe kein echtes biologisches Alter.",
        "tone_summary": "praezise, pruefungsnah und etwas strenger",
    },
}
COHERENCE_FACT_LABELS: list[tuple[str, str]] = [
    ("user_name", "Nutzername"),
    ("user_city", "Wohnort"),
    ("user_country", "Herkunft"),
    ("user_age", "Alter"),
    ("user_job", "Beruf"),
    ("user_goal_exam", "Zielpruefung"),
    ("user_goal_level", "Zielniveau"),
]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None
    level: str = Field(default=DEFAULT_LEVEL, pattern=LEVEL_PATTERN)
    persona_key: str | None = Field(default=None, max_length=40)


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str


class FinishRequest(BaseModel):
    conversation_id: str = Field(min_length=1)


class TutorStreamCommitRequest(BaseModel):
    conversation_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=2000)
    reply: str = Field(min_length=1)
    level: str = Field(default=DEFAULT_LEVEL, pattern=LEVEL_PATTERN)


class TutorTtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    turn_id: str | None = None
    sentence_index: int = Field(default=0, ge=0)
    persona_key: str | None = Field(default=None, max_length=40)


class TranscriptEntry(BaseModel):
    id: str
    role: TranscriptRole
    text: str
    timestamp: str
    created_at: str | None = None
    status: TranscriptStatus = "active"
    reply_to_id: str | None = None
    version_group_id: str | None = None
    version_index: int = 1
    edited_from_id: str | None = None
    invalidated_by_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class TranscriptResponse(BaseModel):
    conversation_id: str
    level: str
    started_at: str
    persona_key: str | None = None
    transcript: list[TranscriptEntry]


class FinishResponse(BaseModel):
    conversation_id: str
    level: str
    transcript: list[TranscriptEntry]
    feedback: str


class TranscriptMutationResponse(BaseModel):
    conversation_id: str
    level: str
    entry_id: str
    assistant_entry_id: str
    invalidated_entry_ids: list[str] = Field(default_factory=list)
    transcript: list[TranscriptEntry]


class MessageVersionsResponse(BaseModel):
    conversation_id: str
    entry_id: str
    active_entry_id: str | None = None
    versions: list[TranscriptEntry]


class TranscribeResponse(BaseModel):
    text: str


class MonologueAnalyzeRequest(BaseModel):
    text: str = Field(min_length=20, max_length=12000)
    level: str = Field(default=DEFAULT_LEVEL, pattern=LEVEL_PATTERN)
    goal_level: str = Field(default="B2", pattern=LEVEL_PATTERN)


class MonologueAnalyzeResponse(BaseModel):
    feedback: str
    estimated_level: str
    goal_level: str
    normalized_text: str
    detected_issues: int


class ExamPracticeRequest(BaseModel):
    level: str = Field(default=DEFAULT_LEVEL, pattern=LEVEL_PATTERN)
    exam: ExamName = "goethe"
    section: ExamSection = "sprechen"
    topic: str | None = Field(default=None, max_length=120)


class ExamPracticeResponse(BaseModel):
    exam: ExamName
    section: ExamSection
    level: str
    title: str
    official_basis: str
    content: str


class PracticeQuestion(BaseModel):
    id: str
    type: Literal["mcq", "cloze", "short", "open"]
    prompt: str
    support_text: str | None = None
    options: list[str] = Field(default_factory=list)
    max_points: int = 1


class ExamMockStartRequest(BaseModel):
    level: str = Field(default=DEFAULT_LEVEL, pattern=LEVEL_PATTERN)
    exam: ExamName = "goethe"
    module: ExamSection = "lesen"
    topic: str | None = Field(default=None, max_length=120)
    question_count: int = Field(default=6, ge=3, le=12)


class ExamMockStartResponse(BaseModel):
    mock_id: str
    exam: ExamName
    module: ExamSection
    level: str
    title: str
    instructions: str
    estimated_minutes: int
    questions: list[PracticeQuestion]


class ExamMockSubmitRequest(BaseModel):
    mock_id: str = Field(min_length=1)
    answers: dict[str, str] = Field(default_factory=dict)


class QuestionEvaluation(BaseModel):
    question_id: str
    prompt: str
    user_answer: str
    correct_answer: str
    score: int
    max_score: int
    is_correct: bool
    feedback: str


class ExamMockSubmitResponse(BaseModel):
    mock_id: str
    exam: ExamName
    module: ExamSection
    level: str
    score: int
    max_score: int
    percent: float
    passed: bool
    summary: str
    results: list[QuestionEvaluation]


class ExerciseSetRequest(BaseModel):
    level: str = Field(default=DEFAULT_LEVEL, pattern=LEVEL_PATTERN)
    focus: ExamSection = "grammatik"
    topic: str | None = Field(default=None, max_length=120)
    count: int = Field(default=8, ge=4, le=14)


class ExerciseSetResponse(BaseModel):
    set_id: str
    level: str
    focus: ExamSection
    title: str
    instructions: str
    questions: list[PracticeQuestion]


class ExerciseSubmitRequest(BaseModel):
    set_id: str = Field(min_length=1)
    answers: dict[str, str] = Field(default_factory=dict)


class ExerciseSubmitResponse(BaseModel):
    set_id: str
    level: str
    focus: ExamSection
    score: int
    max_score: int
    percent: float
    summary: str
    results: list[QuestionEvaluation]


class FlashcardsGenerateRequest(BaseModel):
    level: str = Field(default=DEFAULT_LEVEL, pattern=LEVEL_PATTERN)
    topic: str = Field(min_length=2, max_length=80)
    count: int = Field(default=12, ge=6, le=30)


class FlashcardItem(BaseModel):
    id: str
    front: str
    back: str
    example: str


class FlashcardsGenerateResponse(BaseModel):
    set_id: str
    level: str
    topic: str
    cards: list[FlashcardItem]
    study_tip: str


class FlashcardCheckRequest(BaseModel):
    set_id: str = Field(min_length=1)
    card_id: str = Field(min_length=1)
    answer: str = Field(min_length=1, max_length=200)


class FlashcardCheckResponse(BaseModel):
    set_id: str
    card_id: str
    is_correct: bool
    expected: str
    feedback: str


class RuntimeConfigResponse(BaseModel):
    provider: Literal["ollama", "rulebased"]
    transcribe_provider: Literal["local", "none"] = "none"
    server_transcribe: bool
    tutor_streaming_enabled: bool = False
    tutor_local_tts_available: bool = False
    tutor_tts_fallback: Literal["browser", "none"] = "browser"
    tutor_tts_voice_label: str | None = None
    llm_required: bool
    active_model: str | None = None
    transcribe_model: str | None = None
    speed_profile: Literal["turbo", "balanced", "quality"] | None = None
    chat_timeout_ms: int = FRONTEND_CHAT_TIMEOUT_MS
    transcribe_timeout_ms: int = FRONTEND_TRANSCRIBE_TIMEOUT_MS


class OllamaTurboResponse(BaseModel):
    running: bool
    target_model: str
    installed: bool
    detail: str


class ConversationSummary(BaseModel):
    conversation_id: str
    level: str
    started_at: str
    last_updated: str
    turns: int
    preview: str


def parse_allowed_origins() -> list[str]:
    raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return origins or ["*"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


GERMAN_WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
GERMAN_MONTHS = [
    "Januar",
    "Februar",
    "Maerz",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]


def now_in_app_timezone() -> datetime:
    try:
        tz = ZoneInfo(APP_TIMEZONE)
        return datetime.now(tz)
    except Exception:
        return datetime.now().astimezone()


def german_now_labels(now: datetime | None = None) -> tuple[str, str]:
    moment = now or now_in_app_timezone()
    weekday = GERMAN_WEEKDAYS[moment.weekday()]
    date_label = f"{weekday}, {moment.day}. {GERMAN_MONTHS[moment.month - 1]} {moment.year}"
    time_label = moment.strftime("%H:%M")
    return date_label, time_label


def runtime_datetime_system_note() -> str:
    date_label, time_label = german_now_labels()
    return (
        f"Aktuelle lokale Zeit ({APP_TIMEZONE}): {date_label}, {time_label}. "
        "Wenn nach Datum/Uhrzeit/Wochentag gefragt wird, antworte exakt mit diesen Angaben."
    )


def clean_env_value(value: str) -> str:
    return value.strip().strip('"').strip("'")


def get_transcribe_provider_preference() -> str:
    raw = os.getenv("TRANSCRIBE_PROVIDER", TRANSCRIBE_PROVIDER).strip().lower()
    valid = {"auto", "local"}
    return raw if raw in valid else "local"


def local_transcribe_available() -> bool:
    return WhisperModel is not None


def current_local_transcribe_model() -> str:
    model_name = os.getenv("LOCAL_TRANSCRIBE_MODEL", LOCAL_TRANSCRIBE_MODEL).strip()
    return model_name or "base"


def current_local_transcribe_device() -> str:
    raw = os.getenv("LOCAL_TRANSCRIBE_DEVICE", LOCAL_TRANSCRIBE_DEVICE).strip().lower()
    if raw == "cuda":
        return "cuda"
    return "cpu"


def current_local_transcribe_compute_type() -> str:
    raw = os.getenv("LOCAL_TRANSCRIBE_COMPUTE_TYPE", LOCAL_TRANSCRIBE_COMPUTE_TYPE).strip().lower()
    return raw or "int8"


def resolve_transcribe_provider() -> Literal["local", "none"]:
    provider = get_transcribe_provider_preference()
    if provider in {"auto", "local"}:
        if local_transcribe_available():
            return "local"
        return "none"
    return "none"


def transcribe_available() -> bool:
    return resolve_transcribe_provider() != "none"


def current_transcribe_model_label(provider: Literal["local", "none"] | None = None) -> str | None:
    resolved = provider or resolve_transcribe_provider()
    if resolved == "local":
        return current_local_transcribe_model()
    return None


def get_local_transcribe_model() -> Any:
    if WhisperModel is None:
        raise RuntimeError(
            "Local transcription dependencies are missing. Run 'pip install -r requirements.txt'."
        )
    model_name = current_local_transcribe_model()
    device = current_local_transcribe_device()
    compute_type = current_local_transcribe_compute_type()
    cache_key = f"{model_name}|{device}|{compute_type}"
    global LOCAL_TRANSCRIBE_INSTANCE
    global LOCAL_TRANSCRIBE_INSTANCE_KEY
    with LOCAL_TRANSCRIBE_LOCK:
        if LOCAL_TRANSCRIBE_INSTANCE is None or LOCAL_TRANSCRIBE_INSTANCE_KEY != cache_key:
            cpu_threads = max(2, (os.cpu_count() or 4) - 1)
            LOCAL_TRANSCRIBE_INSTANCE = WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type,
                cpu_threads=cpu_threads,
            )
            LOCAL_TRANSCRIBE_INSTANCE_KEY = cache_key
    return LOCAL_TRANSCRIBE_INSTANCE


def normalize_transcribe_language(language: str | None) -> str | None:
    cleaned = str(language or "").strip().lower()
    if not cleaned or cleaned == "auto":
        return None
    if cleaned.startswith("de"):
        return "de"
    return cleaned


def infer_audio_suffix(filename: str, content_type: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix:
        return suffix
    content_map = {
        "audio/webm": ".webm",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/mp4": ".m4a",
        "audio/aac": ".aac",
        "audio/ogg": ".ogg",
        "audio/flac": ".flac",
    }
    return content_map.get(content_type.lower(), ".webm")


def transcribe_with_local_model(
    *,
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    language: str,
) -> str:
    model = get_local_transcribe_model()
    temp_path: Path | None = None
    try:
        suffix = infer_audio_suffix(filename, content_type)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(audio_bytes)
            temp_path = Path(tmp_file.name)
        segments, _ = model.transcribe(
            str(temp_path),
            language=normalize_transcribe_language(language),
            task="transcribe",
            beam_size=LOCAL_TRANSCRIBE_BEAM_SIZE,
            vad_filter=LOCAL_TRANSCRIBE_VAD_FILTER,
            condition_on_previous_text=False,
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        return text
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Local transcription failed: {exc}") from exc
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def get_provider_preference() -> str:
    raw = os.getenv("CHAT_PROVIDER", CHAT_PROVIDER).strip().lower()
    valid = {"auto", "ollama", "rulebased"}
    return raw if raw in valid else "auto"


def _copy_transcript_entry(entry: TranscriptEntryDict) -> TranscriptEntryDict:
    copied: TranscriptEntryDict = dict(entry)
    copied["meta"] = dict(entry.get("meta") or {})
    return copied


def _clean_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _normalize_transcript_status(value: Any) -> TranscriptStatus:
    status = str(value or "active").strip().lower()
    return status if status in {"active", "superseded", "outdated"} else "active"


def _version_group_counter_seed(group_id: str | None) -> int:
    if not group_id:
        return 0
    match = re.fullmatch(r"vg-(\d+)", str(group_id).strip())
    if not match:
        return 0
    return int(match.group(1))


def _new_transcript_entry_id() -> str:
    return uuid4().hex


def _next_version_group_id(session: SessionState) -> str:
    next_index = int(session.get("next_version_group_index") or 1)
    session["next_version_group_index"] = next_index + 1
    return f"vg-{next_index}"


def _active_transcript_entries(transcript: list[TranscriptEntryDict]) -> list[TranscriptEntryDict]:
    return [_copy_transcript_entry(item) for item in transcript if item.get("status", "active") == "active"]


def get_active_transcript(session: SessionState) -> list[TranscriptEntryDict]:
    return _active_transcript_entries(session.get("transcript", []))


def build_transcript_response_entries(transcript: list[TranscriptEntryDict]) -> list[TranscriptEntry]:
    return [TranscriptEntry(**_copy_transcript_entry(item)) for item in transcript]


def _normalize_tutor_persona_key(value: Any) -> TutorPersonaKey | None:
    candidate = str(value or "").strip().lower()
    if candidate in TUTOR_PERSONA_REGISTRY:
        return cast(TutorPersonaKey, candidate)
    return None


def _copy_session_coherence(coherence: SessionCoherenceDict | dict[str, Any] | None) -> SessionCoherenceDict:
    raw = coherence if isinstance(coherence, dict) else {}
    return {
        "persona_key": _normalize_tutor_persona_key(raw.get("persona_key")) or DEFAULT_TUTOR_PERSONA,
        "assistant_facts": dict(raw.get("assistant_facts") or {}),
        "conversation_facts": dict(raw.get("conversation_facts") or {}),
        "last_rebuilt_at": str(raw.get("last_rebuilt_at") or ""),
    }


def build_assistant_facts(persona_key: TutorPersonaKey | None) -> dict[str, str]:
    resolved = _normalize_tutor_persona_key(persona_key) or DEFAULT_TUTOR_PERSONA
    return dict(TUTOR_PERSONA_REGISTRY[resolved])


def _clean_fact_value(value: str) -> str:
    return str(value or "").strip(" \t\r\n.,;:!?\"'()[]{}")


def _extract_first_fact(patterns: list[re.Pattern[str]], text: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        value = _clean_fact_value(match.group(1))
        if value:
            return value
    return None


USER_NAME_PATTERNS = [
    re.compile(r"\bich hei(?:ss|ß)e\s+([A-Za-zÄÖÜäöüß-]+)", flags=re.IGNORECASE),
    re.compile(r"\bmein name ist\s+([A-Za-zÄÖÜäöüß-]+)", flags=re.IGNORECASE),
]
USER_CITY_PATTERNS = [
    re.compile(r"\bich wohne in\s+([A-Za-zÄÖÜäöüß-]+)", flags=re.IGNORECASE),
    re.compile(r"\bich lebe in\s+([A-Za-zÄÖÜäöüß-]+)", flags=re.IGNORECASE),
]
USER_COUNTRY_PATTERNS = [
    re.compile(r"\bich komme aus\s+([A-Za-zÄÖÜäöüß-]+)", flags=re.IGNORECASE),
    re.compile(r"\bich bin aus\s+([A-Za-zÄÖÜäöüß-]+)", flags=re.IGNORECASE),
]
USER_AGE_PATTERNS = [
    re.compile(r"\bich bin\s+(\d{1,3})\s+jahre\s+alt\b", flags=re.IGNORECASE),
]
USER_JOB_PATTERNS = [
    re.compile(r"\bich arbeite als\s+([A-Za-zÄÖÜäöüß -]+)", flags=re.IGNORECASE),
    re.compile(r"\bich bin\s+([A-Za-zÄÖÜäöüß -]+)\s+von beruf\b", flags=re.IGNORECASE),
]


def extract_conversation_facts_from_transcript(transcript: list[TranscriptEntryDict]) -> dict[str, str]:
    facts: dict[str, str] = {}
    for item in transcript:
        if item.get("role") != "user":
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        normalized = normalize_for_matching(text)

        user_name = _extract_first_fact(USER_NAME_PATTERNS, text)
        if user_name:
            facts["user_name"] = user_name

        user_city = _extract_first_fact(USER_CITY_PATTERNS, text)
        if user_city:
            facts["user_city"] = user_city

        user_country = _extract_first_fact(USER_COUNTRY_PATTERNS, text)
        if user_country:
            facts["user_country"] = user_country

        user_age = _extract_first_fact(USER_AGE_PATTERNS, text)
        if user_age:
            facts["user_age"] = user_age

        user_job = _extract_first_fact(USER_JOB_PATTERNS, text)
        if user_job:
            facts["user_job"] = user_job

        if re.search(r"\b(ziel|moechte|will|pruefung|pruefe|vorbereite)\b", normalized):
            exam_match = re.search(r"\b(goethe|telc|oesd|testdaf)\b", normalized)
            if exam_match:
                facts["user_goal_exam"] = exam_match.group(1)
            level_match = re.search(r"\b(a1|a2|b1|b2|c1|c2)\b", normalized, flags=re.IGNORECASE)
            if level_match:
                facts["user_goal_level"] = level_match.group(1).upper()
    return facts


def build_transcript_coherence(
    transcript: list[TranscriptEntryDict],
    *,
    persona_key: TutorPersonaKey | None = None,
) -> SessionCoherenceDict:
    resolved_persona = _normalize_tutor_persona_key(persona_key) or DEFAULT_TUTOR_PERSONA
    return {
        "persona_key": resolved_persona,
        "assistant_facts": build_assistant_facts(resolved_persona),
        "conversation_facts": extract_conversation_facts_from_transcript(transcript),
        "last_rebuilt_at": utc_now_iso(),
    }


def ensure_session_coherence_locked(
    session: SessionState,
    *,
    requested_persona_key: str | None = None,
    rebuild: bool = False,
) -> SessionCoherenceDict:
    raw = session.get("coherence")
    current_persona = _normalize_tutor_persona_key((raw or {}).get("persona_key") if isinstance(raw, dict) else None)
    resolved_persona = current_persona or _normalize_tutor_persona_key(requested_persona_key) or DEFAULT_TUTOR_PERSONA
    should_rebuild = rebuild or not isinstance(raw, dict) or not current_persona
    if should_rebuild:
        session["coherence"] = build_transcript_coherence(
            get_active_transcript(session),
            persona_key=resolved_persona,
        )
    return _copy_session_coherence(session.get("coherence"))


def build_preview_coherence(
    session: SessionState,
    transcript: list[TranscriptEntryDict],
    *,
    requested_persona_key: str | None = None,
) -> SessionCoherenceDict:
    raw = session.get("coherence")
    resolved_persona = (
        _normalize_tutor_persona_key((raw or {}).get("persona_key") if isinstance(raw, dict) else None)
        or _normalize_tutor_persona_key(requested_persona_key)
        or DEFAULT_TUTOR_PERSONA
    )
    return build_transcript_coherence(transcript, persona_key=resolved_persona)


def rebuild_session_coherence(conversation_id: str) -> None:
    with SESSIONS_LOCK:
        session = SESSIONS.get(conversation_id)
        if not session:
            return
        ensure_session_coherence_locked(session, rebuild=True)
    schedule_state_persist()


def build_chat_coherence_system_note(coherence: SessionCoherenceDict | dict[str, Any] | None) -> str | None:
    if not isinstance(coherence, dict):
        return None
    normalized_coherence = _copy_session_coherence(coherence)
    assistant_facts = normalized_coherence.get("assistant_facts") or {}
    conversation_facts = normalized_coherence.get("conversation_facts") or {}
    parts: list[str] = [
        "Aktive Gespraechskoharenz:",
        f"Persona bleibt: {assistant_facts.get('persona_title', DEFAULT_TUTOR_PERSONA)}.",
        f"Tutor-Identitaet: {assistant_facts.get('identity_summary', 'Ich bin dein digitaler Deutsch-Tutor.')}",
        f"Tutor-Herkunft: {assistant_facts.get('origin_summary', 'Ich bin digital und habe keinen festen Wohnort.')}",
        f"Tutor-Alter: {assistant_facts.get('age_summary', 'Ich habe kein echtes biologisches Alter.')}",
    ]
    fact_parts = [
        f"{label}: {conversation_facts[key]}"
        for key, label in COHERENCE_FACT_LABELS
        if conversation_facts.get(key)
    ]
    if fact_parts:
        parts.append("Aktive Chat-Fakten: " + "; ".join(fact_parts) + ".")
    parts.append(
        "Widersprich diesen aktiven Fakten nicht. Wenn der Nutzer sie explizit aendert, gilt die neueste aktive Aussage."
    )
    return " ".join(parts)


def find_transcript_entry(
    session: SessionState,
    entry_id: str,
    *,
    role: TranscriptRole | None = None,
) -> TranscriptEntryDict | None:
    target_id = str(entry_id or "").strip()
    if not target_id:
        return None
    for item in session.get("transcript", []):
        if item.get("id") != target_id:
            continue
        if role and item.get("role") != role:
            continue
        return item
    return None


def get_active_entry_ids(session: SessionState) -> set[str]:
    return {
        str(item.get("id"))
        for item in session.get("transcript", [])
        if item.get("status", "active") == "active" and str(item.get("id", "")).strip()
    }


def get_active_user_entry_for_version_group(session: SessionState, version_group_id: str) -> TranscriptEntryDict | None:
    for item in session.get("transcript", []):
        if (
            item.get("role") == "user"
            and item.get("status", "active") == "active"
            and item.get("version_group_id") == version_group_id
        ):
            return item
    return None


def list_user_versions(session: SessionState, version_group_id: str) -> list[TranscriptEntryDict]:
    versions = [
        _copy_transcript_entry(item)
        for item in session.get("transcript", [])
        if item.get("role") == "user" and item.get("version_group_id") == version_group_id
    ]
    versions.sort(
        key=lambda item: (
            int(item.get("version_index") or 1),
            str(item.get("created_at") or item.get("timestamp") or ""),
        )
    )
    return versions


def find_active_assistant_reply(session: SessionState, user_entry_id: str) -> TranscriptEntryDict | None:
    for item in session.get("transcript", []):
        if (
            item.get("role") == "assistant"
            and item.get("status", "active") == "active"
            and item.get("reply_to_id") == user_entry_id
        ):
            return item
    return None


def mark_transcript_entry_status(
    entry: TranscriptEntryDict,
    *,
    status: TranscriptStatus,
    invalidated_by_id: str | None = None,
) -> None:
    entry["status"] = status
    entry["invalidated_by_id"] = _clean_optional_str(invalidated_by_id)


def invalidate_active_entries_after(
    session: SessionState,
    *,
    start_entry_id: str,
    invalidated_by_id: str,
) -> list[str]:
    invalidated_ids: list[str] = []
    seen_start = False
    for item in session.get("transcript", []):
        if not seen_start:
            if item.get("id") == start_entry_id:
                seen_start = True
            continue
        if item.get("status", "active") != "active":
            continue
        mark_transcript_entry_status(item, status="outdated", invalidated_by_id=invalidated_by_id)
        entry_id = _clean_optional_str(item.get("id"))
        if entry_id:
            invalidated_ids.append(entry_id)
    return invalidated_ids


def build_active_transcript_up_to_entry(
    session: SessionState,
    entry_id: str,
) -> list[TranscriptEntryDict]:
    target_id = str(entry_id or "").strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="Entry id is required.")
    active_entries = get_active_transcript(session)
    prefix: list[TranscriptEntryDict] = []
    for item in active_entries:
        prefix.append(item)
        if item.get("id") == target_id:
            return prefix
    raise HTTPException(status_code=404, detail="Active transcript entry not found.")


def session_last_updated(session: SessionState) -> str:
    active_transcript = get_active_transcript(session)
    if active_transcript:
        return str(active_transcript[-1].get("timestamp") or active_transcript[-1].get("created_at") or session["started_at"])
    if session["transcript"]:
        return str(session["transcript"][-1].get("timestamp") or session["transcript"][-1].get("created_at") or session["started_at"])
    return session["started_at"]


def session_preview(session: SessionState) -> str:
    active_transcript = get_active_transcript(session)
    for item in reversed(active_transcript):
        if item["role"] == "user" and item["text"].strip():
            return item["text"].strip()[:120]
    if active_transcript:
        return active_transcript[-1]["text"].strip()[:120]
    if session["transcript"]:
        return str(session["transcript"][-1].get("text", "")).strip()[:120]
    return ""


def trim_transcript_for_model(
    transcript: list[TranscriptEntryDict],
    max_messages: int = OLLAMA_MAX_HISTORY_MESSAGES,
    max_chars: int = CHAT_HISTORY_CHAR_BUDGET,
) -> list[TranscriptEntryDict]:
    trimmed = list(transcript)
    if max_messages > 0 and len(trimmed) > max_messages:
        trimmed = trimmed[-max_messages:]
    if max_chars > 0 and trimmed:
        selected: list[TranscriptEntryDict] = []
        used_chars = 0
        for item in reversed(trimmed):
            item_len = len(item["text"])
            if selected and used_chars + item_len > max_chars:
                break
            selected.append(item)
            used_chars += item_len
        trimmed = list(reversed(selected)) if selected else [trimmed[-1]]
    if len(trimmed) > 1 and trimmed[0]["role"] == "assistant":
        trimmed = trimmed[1:]
    return trimmed


def _safe_level(value: str) -> str:
    level = str(value or DEFAULT_LEVEL).strip().upper()
    if re.fullmatch(LEVEL_PATTERN, level):
        return level
    return DEFAULT_LEVEL


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _snapshot_state_for_persistence() -> dict[str, Any]:
    with SESSIONS_LOCK:
        sessions_copy = {
            cid: {
                "level": session["level"],
                "started_at": session["started_at"],
                "next_version_group_index": int(session.get("next_version_group_index") or 1),
                "transcript": [_copy_transcript_entry(item) for item in session["transcript"]],
                "coherence": _copy_session_coherence(ensure_session_coherence_locked(session)),
            }
            for cid, session in SESSIONS.items()
        }
    with PROFILE_LOCK:
        profile_copy = {
            "topic_counts": dict(LEARNER_PROFILE["topic_counts"]),
            "common_corrections": dict(LEARNER_PROFILE["common_corrections"]),
            "total_user_messages": int(LEARNER_PROFILE["total_user_messages"]),
            "last_updated": LEARNER_PROFILE["last_updated"],
        }
    return {"sessions": sessions_copy, "learner_profile": profile_copy}


def persist_state_to_disk() -> None:
    state_payload = _snapshot_state_for_persistence()
    _atomic_write_json(STATE_FILE, state_payload)


def _flush_scheduled_state_persist() -> None:
    global STATE_PERSIST_DIRTY, STATE_PERSIST_TIMER
    with STATE_PERSIST_LOCK:
        dirty = STATE_PERSIST_DIRTY
        STATE_PERSIST_DIRTY = False
        STATE_PERSIST_TIMER = None
    if not dirty:
        return
    try:
        persist_state_to_disk()
    except Exception as exc:  # pragma: no cover - disk/system dependent
        logger.warning("state.persist.failed error=%s", exc)
        with STATE_PERSIST_LOCK:
            STATE_PERSIST_DIRTY = True


def schedule_state_persist(delay_ms: int = STATE_PERSIST_DEBOUNCE_MS) -> None:
    global STATE_PERSIST_DIRTY, STATE_PERSIST_TIMER
    if delay_ms <= 0:
        with STATE_PERSIST_LOCK:
            STATE_PERSIST_DIRTY = True
        _flush_scheduled_state_persist()
        return
    with STATE_PERSIST_LOCK:
        STATE_PERSIST_DIRTY = True
        if STATE_PERSIST_TIMER is not None and STATE_PERSIST_TIMER.is_alive():
            return
        STATE_PERSIST_TIMER = Timer(delay_ms / 1000.0, _flush_scheduled_state_persist)
        STATE_PERSIST_TIMER.daemon = True
        STATE_PERSIST_TIMER.start()


def flush_pending_state_persist(force: bool = False) -> None:
    global STATE_PERSIST_DIRTY, STATE_PERSIST_TIMER
    timer: Timer | None
    with STATE_PERSIST_LOCK:
        timer = STATE_PERSIST_TIMER
        STATE_PERSIST_TIMER = None
        if force:
            STATE_PERSIST_DIRTY = True
        dirty = STATE_PERSIST_DIRTY
    if timer is not None and timer.is_alive():
        timer.cancel()
    if dirty:
        _flush_scheduled_state_persist()


def _parse_session_state(raw_session: Any) -> SessionState | None:
    if not isinstance(raw_session, dict):
        return None
    level = _safe_level(str(raw_session.get("level", DEFAULT_LEVEL)))
    started_at = str(raw_session.get("started_at") or datetime.now(timezone.utc).isoformat())
    next_version_group_index_raw = raw_session.get("next_version_group_index", 1)
    next_version_group_index = next_version_group_index_raw if isinstance(next_version_group_index_raw, int) and next_version_group_index_raw >= 1 else 1
    transcript_raw = raw_session.get("transcript", [])
    transcript: list[TranscriptEntryDict] = []
    last_user_entry: TranscriptEntryDict | None = None
    if isinstance(transcript_raw, list):
        for item in transcript_raw:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            if role not in {"user", "assistant"}:
                continue
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            created_at = str(item.get("created_at") or item.get("timestamp") or started_at)
            timestamp = str(item.get("timestamp") or created_at)
            entry_id = _clean_optional_str(item.get("id")) or _new_transcript_entry_id()
            status = _normalize_transcript_status(item.get("status"))
            version_group_id = _clean_optional_str(item.get("version_group_id"))
            version_index_raw = item.get("version_index", 1)
            version_index = version_index_raw if isinstance(version_index_raw, int) and version_index_raw >= 1 else 1
            raw_meta = item.get("meta")
            meta_source = str((raw_meta.get("source") if isinstance(raw_meta, dict) else "") or "legacy").strip() or "legacy"
            if role == "user":
                if not version_group_id:
                    version_group_id = f"vg-{next_version_group_index}"
                    next_version_group_index += 1
                last_user_entry = {
                    "id": entry_id,
                    "role": role,
                    "text": text,
                    "timestamp": timestamp,
                    "created_at": created_at,
                    "status": status,
                    "reply_to_id": None,
                    "version_group_id": version_group_id,
                    "version_index": version_index,
                    "edited_from_id": _clean_optional_str(item.get("edited_from_id")),
                    "invalidated_by_id": _clean_optional_str(item.get("invalidated_by_id")),
                    "meta": {"source": meta_source},
                }
                transcript.append(last_user_entry)
            else:
                if not version_group_id and last_user_entry:
                    version_group_id = str(last_user_entry.get("version_group_id") or "")
                if not version_group_id:
                    version_group_id = f"vg-{next_version_group_index}"
                    next_version_group_index += 1
                if (not isinstance(version_index_raw, int) or version_index_raw < 1) and last_user_entry:
                    version_index = int(last_user_entry.get("version_index") or 1)
                transcript.append(
                    {
                        "id": entry_id,
                        "role": role,
                        "text": text,
                        "timestamp": timestamp,
                        "created_at": created_at,
                        "status": status,
                        "reply_to_id": _clean_optional_str(item.get("reply_to_id")) or (last_user_entry.get("id") if last_user_entry else None),
                        "version_group_id": version_group_id,
                        "version_index": version_index,
                        "edited_from_id": _clean_optional_str(item.get("edited_from_id")),
                        "invalidated_by_id": _clean_optional_str(item.get("invalidated_by_id")),
                        "meta": {"source": meta_source},
                    }
                )
            next_version_group_index = max(next_version_group_index, _version_group_counter_seed(version_group_id) + 1)
    raw_coherence = raw_session.get("coherence", {})
    parsed_persona = _normalize_tutor_persona_key(raw_coherence.get("persona_key") if isinstance(raw_coherence, dict) else None)
    coherence = build_transcript_coherence(transcript, persona_key=parsed_persona)
    return {
        "level": level,
        "started_at": started_at,
        "transcript": transcript,
        "next_version_group_index": max(1, next_version_group_index),
        "coherence": coherence,
    }


def load_state_from_disk() -> None:
    if not STATE_FILE.exists():
        return
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return

    loaded_sessions: dict[str, SessionState] = {}
    raw_sessions = raw.get("sessions", {})
    if isinstance(raw_sessions, dict):
        for cid, raw_session in raw_sessions.items():
            if not isinstance(cid, str) or not cid.strip():
                continue
            parsed = _parse_session_state(raw_session)
            if parsed:
                loaded_sessions[cid] = parsed

    raw_profile = raw.get("learner_profile", {})
    loaded_profile: LearnerProfile = {
        "topic_counts": {},
        "common_corrections": {},
        "total_user_messages": 0,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    if isinstance(raw_profile, dict):
        topic_counts = raw_profile.get("topic_counts", {})
        if isinstance(topic_counts, dict):
            loaded_profile["topic_counts"] = {
                str(k): int(v)
                for k, v in topic_counts.items()
                if isinstance(k, str) and str(k).strip() and isinstance(v, int) and v > 0
            }
        correction_counts = raw_profile.get("common_corrections", {})
        if isinstance(correction_counts, dict):
            loaded_profile["common_corrections"] = {
                str(k): int(v)
                for k, v in correction_counts.items()
                if isinstance(k, str) and str(k).strip() and isinstance(v, int) and v > 0
            }
        total_messages = raw_profile.get("total_user_messages", 0)
        if isinstance(total_messages, int) and total_messages >= 0:
            loaded_profile["total_user_messages"] = total_messages
        last_updated = raw_profile.get("last_updated")
        if isinstance(last_updated, str) and last_updated.strip():
            loaded_profile["last_updated"] = last_updated

    with SESSIONS_LOCK:
        SESSIONS.clear()
        SESSIONS.update(loaded_sessions)
    with PROFILE_LOCK:
        LEARNER_PROFILE.clear()
        LEARNER_PROFILE.update(loaded_profile)


def get_session_snapshot(conversation_id: str) -> SessionState | None:
    with SESSIONS_LOCK:
        session = SESSIONS.get(conversation_id)
        if not session:
            return None
        coherence = ensure_session_coherence_locked(session)
        return {
            "level": session["level"],
            "started_at": session["started_at"],
            "next_version_group_index": int(session.get("next_version_group_index") or 1),
            "transcript": [_copy_transcript_entry(item) for item in session["transcript"]],
            "coherence": coherence,
        }


def list_conversation_summaries(limit: int = 200) -> list[ConversationSummary]:
    with SESSIONS_LOCK:
        items = [
            (cid, session_last_updated(session), session)
            for cid, session in SESSIONS.items()
        ]

    items.sort(key=lambda row: row[1], reverse=True)
    summaries: list[ConversationSummary] = []
    for cid, last_updated, session in items[:limit]:
        active_transcript = get_active_transcript(session)
        turns = sum(1 for item in active_transcript if item["role"] == "user")
        summaries.append(
            ConversationSummary(
                conversation_id=cid,
                level=session["level"],
                started_at=session["started_at"],
                last_updated=last_updated,
                turns=turns,
                preview=session_preview(session),
            )
        )
    return summaries


def ensure_session(
    conversation_id: str,
    level: str,
    requested_persona_key: str | None = None,
) -> SessionState:
    created = False
    with SESSIONS_LOCK:
        session = SESSIONS.get(conversation_id)
        if not session:
            session = {
                "level": _safe_level(level),
                "started_at": utc_now_iso(),
                "transcript": [],
                "next_version_group_index": 1,
            }
            SESSIONS[conversation_id] = session
            created = True
        elif session["level"] != _safe_level(session["level"]):
            session["level"] = _safe_level(session["level"])
        if not isinstance(session.get("next_version_group_index"), int) or int(session.get("next_version_group_index") or 0) < 1:
            session["next_version_group_index"] = 1
        ensure_session_coherence_locked(session, requested_persona_key=requested_persona_key)
    if created:
        schedule_state_persist()
    with SESSIONS_LOCK:
        session = SESSIONS[conversation_id]
        return session


def _build_transcript_entry_record(
    session: SessionState,
    *,
    role: TranscriptRole,
    text: str,
    entry_id: str | None = None,
    reply_to_id: str | None = None,
    version_group_id: str | None = None,
    version_index: int | None = None,
    edited_from_id: str | None = None,
    status: TranscriptStatus = "active",
    invalidated_by_id: str | None = None,
    meta_source: str = "blocking",
    created_at: str | None = None,
) -> TranscriptEntryDict:
    created_at_value = _clean_optional_str(created_at) or utc_now_iso()
    resolved_version_group_id = _clean_optional_str(version_group_id)
    resolved_reply_to_id = _clean_optional_str(reply_to_id)
    resolved_version_index = version_index if isinstance(version_index, int) and version_index >= 1 else None
    if role == "user":
        if not resolved_version_group_id:
            resolved_version_group_id = _next_version_group_id(session)
        if resolved_version_index is None:
            resolved_version_index = 1
        resolved_reply_to_id = None
    else:
        reply_source = find_transcript_entry(session, resolved_reply_to_id or "", role="user") if resolved_reply_to_id else None
        if not resolved_version_group_id and reply_source:
            resolved_version_group_id = _clean_optional_str(reply_source.get("version_group_id"))
        if not resolved_version_group_id:
            resolved_version_group_id = _next_version_group_id(session)
        if resolved_version_index is None:
            resolved_version_index = int(reply_source.get("version_index") or 1) if reply_source else 1
    return {
        "id": _clean_optional_str(entry_id) or _new_transcript_entry_id(),
        "role": role,
        "text": text,
        "timestamp": created_at_value,
        "created_at": created_at_value,
        "status": status,
        "reply_to_id": resolved_reply_to_id,
        "version_group_id": resolved_version_group_id,
        "version_index": int(resolved_version_index or 1),
        "edited_from_id": _clean_optional_str(edited_from_id),
        "invalidated_by_id": _clean_optional_str(invalidated_by_id),
        "meta": {"source": meta_source or "blocking"},
    }


def _append_transcript_entry_locked(session: SessionState, entry: TranscriptEntryDict) -> None:
    session.setdefault("transcript", []).append(entry)


def append_transcript(
    conversation_id: str,
    level: str,
    role: TranscriptRole,
    text: str,
    *,
    entry_id: str | None = None,
    reply_to_id: str | None = None,
    version_group_id: str | None = None,
    version_index: int | None = None,
    edited_from_id: str | None = None,
    status: TranscriptStatus = "active",
    invalidated_by_id: str | None = None,
    meta_source: str = "blocking",
    update_profile: bool = True,
) -> TranscriptEntryDict | None:
    clean_text = text.strip()
    if not clean_text:
        return None
    entry: TranscriptEntryDict | None = None
    with SESSIONS_LOCK:
        session = SESSIONS.get(conversation_id)
        if not session:
            session = {
                "level": _safe_level(level),
                "started_at": utc_now_iso(),
                "transcript": [],
                "next_version_group_index": 1,
            }
            SESSIONS[conversation_id] = session
        entry = _build_transcript_entry_record(
            session,
            role=role,
            text=clean_text,
            entry_id=entry_id,
            reply_to_id=reply_to_id,
            version_group_id=version_group_id,
            version_index=version_index,
            edited_from_id=edited_from_id,
            status=status,
            invalidated_by_id=invalidated_by_id,
            meta_source=meta_source,
        )
        _append_transcript_entry_locked(session, entry)
    if role == "user" and update_profile:
        update_learner_profile_from_user_turn(clean_text)
    schedule_state_persist()
    return _copy_transcript_entry(entry) if entry else None


def transcript_to_prompt(transcript: list[TranscriptEntryDict]) -> str:
    lines: list[str] = []
    for item in transcript:
        speaker = "Alumno" if item["role"] == "user" else "Tutor"
        lines.append(f"{item['timestamp']} | {speaker}: {item['text']}")
    return "\n".join(lines)


def transcript_to_chat_messages(transcript: list[TranscriptEntryDict]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for item in transcript:
        role = "assistant" if item["role"] == "assistant" else "user"
        messages.append({"role": role, "content": item["text"]})
    return messages


FOLLOWUP_BANK: dict[str, list[str]] = {
    "A1": [
        "Erzahl mir noch einen einfachen Satz dazu.",
        "Und was machst du danach?",
        "Wie fuehlst du dich dabei?",
        "Kannst du ein kleines Beispiel geben?",
    ],
    "A2": [
        "Kannst du das etwas genauer beschreiben?",
        "Wie war das fuer dich persoenlich?",
        "Was passierte danach?",
        "Was denkst du darueber?",
    ],
    "B1": [
        "Wie war das fuer dich genau?",
        "Was fandest du daran besonders interessant?",
        "Was ist danach passiert?",
        "Was moechtest du dazu noch sagen?",
    ],
    "B2": [
        "Welche Gruende sprechen aus deiner Sicht dafuer und dagegen?",
        "Wie wuerdest du das jemandem erklaeren, der anderer Meinung ist?",
        "Welche Alternative waere realistisch gewesen?",
        "Was ist dabei fuer dich am wichtigsten?",
    ],
    "C1": [
        "Welche Nuance moechtest du noch praezisieren?",
        "Kannst du das mit einem konkreten Beispiel untermauern?",
        "Welche Gegenposition ist hier am staerksten?",
        "Welche Schlussfolgerung ziehst du daraus?",
    ],
    "C2": [
        "Welche impliziten Annahmen siehst du in deiner Position?",
        "Wie aendert sich dein Argument in einem anderen Kontext?",
        "Kannst du ein praezises Gegenbeispiel formulieren?",
        "Fass deinen Kernpunkt in zwei klaren Saetzen zusammen.",
    ],
}

ACK_BANK: dict[str, list[str]] = {
    "A1": ["Sehr gut.", "Cool, danke.", "Das klingt gut."],
    "A2": ["Interessant, danke.", "Verstehe, das klingt spannend.", "Schoen beschrieben."],
    "B1": ["Spannend, ich verstehe.", "Danke, das klingt interessant.", "Okay, ich kann dir folgen."],
    "B2": ["Das ist ein differenzierter Punkt.", "Interessante Perspektive.", "Guter Gedanke."],
    "C1": [
        "Das ist inhaltlich sehr stark.",
        "Das ist eine praezise Beobachtung.",
        "Gute, differenzierte Aussage.",
    ],
    "C2": ["Das ist argumentativ sehr klar.", "Starke Formulierung.", "Das ist ein nuancierter Standpunkt."],
}

GENERIC_REFLECTIONS = [
    "Erzaehl mir mehr dazu.",
    "Das klingt nach einer echten Alltagssituation.",
    "Ich kann dir gut folgen.",
    "Das Thema ist wirklich interessant.",
]

GERMAN_TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß']+")

GERMAN_STOPWORDS = {
    "aber",
    "alles",
    "auch",
    "bei",
    "bin",
    "bist",
    "dann",
    "das",
    "dass",
    "dein",
    "deine",
    "dem",
    "den",
    "der",
    "des",
    "die",
    "du",
    "ein",
    "eine",
    "einer",
    "einem",
    "es",
    "fuer",
    "hat",
    "habe",
    "hast",
    "heute",
    "ich",
    "im",
    "in",
    "ist",
    "ja",
    "kein",
    "keine",
    "mein",
    "meinen",
    "meine",
    "deinen",
    "seinen",
    "ihren",
    "unseren",
    "mit",
    "moechte",
    "mochtest",
    "nach",
    "nicht",
    "noch",
    "oder",
    "uber",
    "ueber",
    "schon",
    "sehr",
    "sie",
    "sind",
    "so",
    "und",
    "war",
    "was",
    "einen",
    "keinen",
    "diesen",
    "wenn",
    "wie",
    "wir",
    "wochenende",
    "zu",
}

TOPIC_KEYWORDS: dict[str, set[str]] = {
    "arbeit": {
        "arbeit",
        "job",
        "firma",
        "kollege",
        "kollegen",
        "chef",
        "buero",
        "meeting",
        "projekt",
        "kunden",
    },
    "lernen": {
        "lernen",
        "deutsch",
        "pruefung",
        "grammatik",
        "wortschatz",
        "schule",
        "studium",
        "uni",
        "b1",
        "b2",
        "c1",
    },
    "familie": {
        "familie",
        "mutter",
        "vater",
        "eltern",
        "bruder",
        "schwester",
        "sohn",
        "tochter",
        "kinder",
    },
    "sport": {
        "sport",
        "fussball",
        "tennis",
        "training",
        "spiel",
        "team",
        "gewonnen",
        "verloren",
        "fitness",
    },
    "essen": {
        "essen",
        "kochen",
        "restaurant",
        "fruehstueck",
        "mittagessen",
        "abendessen",
        "rezept",
        "kaffee",
    },
    "reise": {
        "reise",
        "reisen",
        "urlaub",
        "flug",
        "hotel",
        "stadt",
        "land",
        "zug",
        "madrid",
        "berlin",
    },
    "konflikt": {
        "streit",
        "konflikt",
        "problem",
        "aerger",
        "diskussion",
        "missverstaendnis",
    },
    "freizeit": {
        "freizeit",
        "hobby",
        "farbe",
        "lieblingsfarbe",
        "film",
        "filme",
        "musik",
        "lesen",
        "serie",
        "serien",
        "spielen",
    },
}

TOPIC_REFLECTIONS: dict[str, list[str]] = {
    "arbeit": ["Du erzaehlst gerade von deiner Arbeit.", "Okay, es geht gerade um deinen Arbeitsalltag."],
    "lernen": ["Du sprichst gerade ueber dein Lernen.", "Verstanden, das Thema ist gerade dein Deutschlernen."],
    "familie": ["Das klingt nach einer Situation mit deiner Familie.", "Okay, es geht um deine Familie."],
    "sport": ["Ah, wir sprechen ueber Sport.", "Alles klar, es geht um dein Team oder ein Spiel."],
    "essen": ["Lecker, es geht also ums Essen oder Kochen.", "Alles klar, das Thema ist Essen."],
    "reise": ["Das klingt nach Reise oder Urlaub.", "Okay, wir sind beim Thema Reisen."],
    "konflikt": ["Das klingt nach einer schwierigen Situation.", "Verstehe, das war ein Konfliktmoment."],
    "freizeit": ["Das klingt nach einem Freizeitthema.", "Okay, wir sprechen ueber deine Freizeit."],
}

TOPIC_QUESTIONS: dict[str, list[str]] = {
    "arbeit": [
        "Was war heute bei der Arbeit am schwierigsten?",
        "Mit wem hast du dort am meisten gesprochen?",
        "Was moechtest du bei der Arbeit als Naechstes verbessern?",
    ],
    "lernen": [
        "Welcher Teil beim Deutschlernen ist fuer dich gerade am schwersten?",
        "Wie bereitest du dich konkret auf die Pruefung vor?",
        "Wovor hast du bei der muendlichen Pruefung am meisten Respekt?",
    ],
    "familie": [
        "Wie war die Stimmung in deiner Familie dabei?",
        "Was habt ihr danach zusammen gemacht?",
        "Wie wichtig ist dir Familienzeit im Alltag?",
    ],
    "sport": [
        "Was war der entscheidende Moment im Spiel?",
        "Welche Position spielst du am liebsten?",
        "Wie hast du dich nach dem Spiel gefuehlt?",
    ],
    "essen": [
        "Was hast du genau gekocht oder gegessen?",
        "Kochst du lieber allein oder mit anderen zusammen?",
        "Welches Gericht willst du als Naechstes ausprobieren?",
    ],
    "reise": [
        "Was hat dir an diesem Ort am besten gefallen?",
        "Mit wem warst du unterwegs?",
        "Wohin willst du als Naechstes reisen?",
    ],
    "konflikt": [
        "Wie hast du in dem Moment reagiert?",
        "Wie wuerdest du das Gespraech heute fuehren?",
        "Was hast du aus dieser Situation gelernt?",
    ],
    "freizeit": [
        "Was macht dir daran am meisten Spass?",
        "Wie oft machst du das normalerweise?",
        "Mit wem teilst du dieses Hobby?",
    ],
}

POSITIVE_EMOTION_WORDS = {
    "gluecklich",
    "froh",
    "zufrieden",
    "motiviert",
    "stolz",
    "entspannt",
    "super",
    "toll",
}

NEGATIVE_EMOTION_WORDS = {
    "angst",
    "stress",
    "nervoes",
    "traurig",
    "frustriert",
    "sorge",
    "sorgen",
    "muede",
    "mued",
}

RULEBASE_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"\bich bin (?P<age>\d{1,3}) jahre\b", flags=re.IGNORECASE),
        "Ich bin {age} Jahre alt.",
        "Con la edad en aleman se usa 'Jahre alt'.",
    ),
    (
        re.compile(r"\bich habe (?P<age>\d{1,3}) jahre alt\b", flags=re.IGNORECASE),
        "Ich bin {age} Jahre alt.",
        "No se dice 'ich habe ... Jahre alt', sino 'ich bin ... Jahre alt'.",
    ),
    (
        re.compile(r"\bich gehe in (?P<place>[a-zA-Z]+)\b", flags=re.IGNORECASE),
        "Ich fahre nach {place}.",
        "Para ir a una ciudad o pais suele sonar mas natural 'fahren nach'.",
    ),
]

SPANISH_HINT_PATTERN = re.compile(
    r"\b(hola|gracias|porque|quiero|hablar|aleman|espanol|hoy)\b", flags=re.IGNORECASE
)

GREETING_ONLY_PATTERN = re.compile(
    r"^\s*(hallo|hi|hey|moin|servus|guten\s+(morgen|tag|abend))\s*[!,.?]*\s*$",
    flags=re.IGNORECASE,
)
HOW_ARE_YOU_PATTERN = re.compile(r"\bwie geht(?:'s| es)\s+(dir|ihnen)\b", flags=re.IGNORECASE)
NAME_QUESTION_PATTERN = re.compile(r"\bwie hei\S*t du\b|\bwer bist du\b", flags=re.IGNORECASE)
THANKS_PATTERN = re.compile(r"\b(danke|vielen dank)\b", flags=re.IGNORECASE)
FAVORITE_COLOR_PATTERN = re.compile(r"\b(lieblingsfarbe|welche farbe)\b", flags=re.IGNORECASE)
AGE_QUESTION_PATTERN = re.compile(r"\bwie alt bist du\b", flags=re.IGNORECASE)
FROM_WHERE_PATTERN = re.compile(
    r"\b(woher kommst du|wo wohnst du|wo lebst du)\b", flags=re.IGNORECASE
)
TIME_QUESTION_PATTERN = re.compile(
    (
        r"\b("
        r"wie spaet ist es|uhrzeit|wie viel uhr|wieviel uhr|welche uhrzeit|"
        r"kannst du mir (?:bitte )?die zeit sagen|"
        r"hast du die zeit"
        r")\b"
    ),
    flags=re.IGNORECASE,
)
DAY_QUESTION_PATTERN = re.compile(
    r"\b(welcher tag|was fuer ein tag|wochentag|heute ist|welcher wochentag)\b",
    flags=re.IGNORECASE,
)
DATE_QUESTION_PATTERN = re.compile(
    r"\b(welches datum|heutiges datum|der wievielte|datum heute)\b",
    flags=re.IGNORECASE,
)
QUESTION_START_PATTERN = re.compile(
    (
        r"^\s*("
        r"wer|wie|was|wo|wann|warum|wieso|weshalb|"
        r"welche|welcher|welches|"
        r"kann|kannst|koennen|hast|haben|habt|"
        r"bist|ist|sind|gibt|gibst|heisst|heißt"
        r")\b"
    ),
    flags=re.IGNORECASE,
)
SIMPLE_ARITHMETIC_PATTERN = re.compile(
    (
        r"^\s*(?:was|wieviel|wie viel)\s+ist\s+"
        r"(?P<a>-?\d+(?:[.,]\d+)?)\s*"
        r"(?P<op>\+|-|\*|x|×|/|:|plus|minus|mal|geteilt\s+durch)\s*"
        r"(?P<b>-?\d+(?:[.,]\d+)?)\s*\??\s*$"
    ),
    flags=re.IGNORECASE,
)
MATH_CAPABILITY_PATTERN = re.compile(
    r"\b(kannst du|kann ich mit dir|kann man mit dir|machst du)\b.*\b(mathe|math|mathematik|rechnen?)\b",
    flags=re.IGNORECASE,
)
SHORT_SENTENCE_HINT_PATTERN = re.compile(
    r"\b(?:short\s+sentences?|kurzen?\s+saetzen?)\b",
    flags=re.IGNORECASE,
)
CONCISE_REPLY_PATTERN = re.compile(
    (
        r"\b("
        r"be concise|be brief|keep it short|short answer|concise answer|"
        r"sei kurz|sei knapp|kurz und knapp|antworte kurz|antworte knapp|kurze antwort"
        r")\b"
    ),
    flags=re.IGNORECASE,
)
SIMPLE_GERMAN_PATTERN = re.compile(
    (
        r"\b("
        r"simple german|easy german|"
        r"einfaches deutsch|einfachem deutsch|leichtes deutsch|leichtem deutsch"
        r")\b"
    ),
    flags=re.IGNORECASE,
)
SENTENCE_COUNT_PATTERNS = [
    re.compile(
        r"\b(?:answer|respond|reply)\s+(?:briefly\s+)?(?:in|with)\s+(?:exactly\s+)?"
        r"(?P<count>1|2|3|one|two|three)\s+(?:short\s+)?sentences?\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:antworte|beantworte|antworten?)\s+(?:bitte\s+)?(?:in|mit)\s+(?:genau\s+)?"
        r"(?P<count>1|2|3|eine[rmn]?|einen|zwei|drei)\s+(?:kurzen?\s+)?saetzen?\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:exactly\s+)?(?P<count>1|2|3|one|two|three)\s+(?:short\s+)?sentences?\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:genau\s+)?(?P<count>1|2|3|eine[rmn]?|einen|zwei|drei)\s+(?:kurzen?\s+)?saetzen?\b",
        flags=re.IGNORECASE,
    ),
]
LEADING_FILLER_PATTERNS = [
    re.compile(r"^\s*das ist (?:ein )?(?:guter|interessanter|spannender|wichtiger) punkt[,.!?:-]*\s*", flags=re.IGNORECASE),
    re.compile(r"^\s*(?:gute|interessante|spannende) frage[,.!?:-]*\s*", flags=re.IGNORECASE),
    re.compile(r"^\s*interessante perspektive[,.!?:-]*\s*", flags=re.IGNORECASE),
]
CLAUSE_BREAK_PATTERN = re.compile(
    (
        r"[,:;]\s+(?=(?:"
        r"aber|und|denn|weil|deshalb|trotzdem|"
        r"ich|wir|du|er|sie|es|man|"
        r"heute|morgen|das|dann|"
        r"mein|meine|dein|deine"
        r")\b)"
    ),
    flags=re.IGNORECASE,
)

ESZETT_WORD_MAP: dict[str, str] = {
    "heisst": "heißt",
    "fussball": "fußball",
    "fuss": "fuß",
    "strasse": "straße",
    "gross": "groß",
}

GERMAN_MATCH_TRANSLATION = str.maketrans(
    {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
    }
)


def _preserve_case(source: str, replacement: str) -> str:
    if source.isupper():
        return replacement.upper().replace("ß", "SS")
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _replace_eszett_words(text: str) -> str:
    output = text
    for raw, target in ESZETT_WORD_MAP.items():
        pattern = re.compile(rf"\b{re.escape(raw)}\b", flags=re.IGNORECASE)
        output = pattern.sub(lambda m: _preserve_case(m.group(0), target), output)
    return output


def normalize_for_matching(text: str) -> str:
    return text.lower().translate(GERMAN_MATCH_TRANSLATION)


def restore_german_text(text: str) -> str:
    # ae/oe are used in this codebase as umlaut fallbacks.
    text = re.sub(r"Ae|AE|ae", lambda m: _preserve_case(m.group(0), "ä"), text)
    text = re.sub(r"Oe|OE|oe", lambda m: _preserve_case(m.group(0), "ö"), text)
    # Convert ue -> ü when it is likely an umlaut fallback (not after a vowel).
    text = re.sub(
        r"(?<![AaEeIiOoUuYyäöüÄÖÜ])Ue|(?<![AaEeIiOoUuYyäöüÄÖÜ])UE|(?<![AaEeIiOoUuYyäöüÄÖÜ])ue",
        lambda m: _preserve_case(m.group(0), "ü"),
        text,
    )
    return _replace_eszett_words(text)


@dataclass(frozen=True)
class ChatReplyConstraints:
    sentence_count: int | None = None
    concise: bool = False
    simple_german: bool = False


SENTENCE_COUNT_LABELS = {
    "1": 1,
    "2": 2,
    "3": 3,
    "one": 1,
    "two": 2,
    "three": 3,
    "eine": 1,
    "einer": 1,
    "einem": 1,
    "einen": 1,
    "zwei": 2,
    "drei": 3,
}


def extract_chat_reply_constraints(message: str) -> ChatReplyConstraints:
    normalized = normalize_for_matching(str(message or "").strip())
    sentence_count: int | None = None
    for pattern in SENTENCE_COUNT_PATTERNS:
        match = pattern.search(normalized)
        if not match:
            continue
        count = SENTENCE_COUNT_LABELS.get(str(match.group("count") or "").lower())
        if count in {1, 2, 3}:
            sentence_count = count
            break
    concise = bool(CONCISE_REPLY_PATTERN.search(normalized) or SHORT_SENTENCE_HINT_PATTERN.search(normalized))
    simple_german = bool(SIMPLE_GERMAN_PATTERN.search(normalized))
    return ChatReplyConstraints(
        sentence_count=sentence_count,
        concise=concise,
        simple_german=simple_german,
    )


def apply_simple_german_level(level: str, constraints: ChatReplyConstraints) -> str:
    if constraints.simple_german and level not in {"A1", "A2"}:
        return "A2"
    return level


def extract_question_segments(message: str) -> list[str]:
    raw = str(message or "").strip()
    if not raw:
        return []

    segments: list[str] = []
    cursor = 0
    for match in re.finditer(r"\?", raw):
        segment = raw[cursor : match.end()].strip()
        cursor = match.end()
        if segment:
            segments.append(segment)

    tail = raw[cursor:].strip()
    if tail and QUESTION_START_PATTERN.match(normalize_for_matching(tail)):
        segments.append(tail)
    elif not segments and QUESTION_START_PATTERN.match(normalize_for_matching(raw)):
        segments.append(raw)

    cleaned_segments: list[str] = []
    for segment in segments:
        cleaned = segment.strip(" \t\r\n\"'“”‘’")
        if cleaned:
            cleaned_segments.append(cleaned)
    return cleaned_segments


def build_chat_constraint_system_note(
    constraints: ChatReplyConstraints,
    message: str = "",
) -> str | None:
    question_segments = extract_question_segments(message)
    has_style_constraint = bool(constraints.sentence_count or constraints.concise or constraints.simple_german)
    if not (has_style_constraint or question_segments):
        return None
    parts: list[str] = ["Aktuelle Nutzer-Vorgabe:"]
    parts.append("Beantworte zuerst die eigentliche Nutzerfrage.")
    if has_style_constraint:
        parts.append(
            "Formulierungen wie 'in 2 Saetzen', 'kurz' oder 'einfaches Deutsch' sind nur Stilvorgaben und keine eigene Frage."
        )
    if len(question_segments) > 1:
        parts.append(
            f"Es wurden {len(question_segments)} Fragen gestellt. Beantworte jede kurz in derselben Reihenfolge."
        )
    elif question_segments:
        parts.append("Gib keine Meta-Antwort und keine Arbeitsanweisung.")
    if question_segments:
        parts.append("Bei einfachen Fakten-, Rechen- oder Faehigkeitsfragen gib die direkte Antwort sofort im ersten Satz.")
    if constraints.sentence_count:
        parts.append(f"Halte genau {constraints.sentence_count} kurze Saetze ein.")
    if constraints.concise:
        parts.append("Sei knapp und direkt. Jeder Satz soll echten Inhalt tragen.")
    if constraints.simple_german:
        parts.append("Nutze sehr einfaches, klares Deutsch mit haeufigen Woertern und kurzen Hauptsaetzen.")
    return " ".join(parts)


def detect_topic(text: str) -> str | None:
    tokens = [normalize_for_matching(token) for token in GERMAN_TOKEN_RE.findall(text)]
    if not tokens:
        return None
    token_set = set(tokens)

    # Prioridad a conflictos explicitos para evitar respuestas de "trabajo normal".
    if token_set.intersection(TOPIC_KEYWORDS["konflikt"]):
        return "konflikt"

    best_topic: str | None = None
    best_score = 0
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = sum(1 for token in tokens if token in keywords)
        if score > best_score:
            best_score = score
            best_topic = topic
    return best_topic


def build_topic_reflection(topic: str | None) -> str:
    if topic and topic in TOPIC_REFLECTIONS:
        return random.choice(TOPIC_REFLECTIONS[topic])
    return random.choice(GENERIC_REFLECTIONS)


def detect_emotion_feedback(text: str) -> str:
    tokens = {normalize_for_matching(token) for token in GERMAN_TOKEN_RE.findall(text)}
    if tokens.intersection(NEGATIVE_EMOTION_WORDS):
        return random.choice(
            [
                "Das klingt ehrlich gesagt ziemlich belastend.",
                "Ich verstehe, das kann echt anstrengend sein.",
                "Das hoert sich nicht leicht an.",
            ]
        )
    if tokens.intersection(POSITIVE_EMOTION_WORDS):
        return random.choice(
            [
                "Das klingt richtig gut.",
                "Schoen, das freut mich fuer dich.",
                "Das hoert sich nach einem guten Moment an.",
            ]
        )
    return ""


def rulebased_followup(level: str, topic: str | None, transcript: list[TranscriptEntryDict]) -> str:
    if topic and topic in TOPIC_QUESTIONS:
        prompts = TOPIC_QUESTIONS[topic]
    else:
        prompts = FOLLOWUP_BANK.get(level, FOLLOWUP_BANK[DEFAULT_LEVEL])

    if not prompts:
        return "Erzaehl mir mehr dazu."

    latest_assistant = ""
    for entry in reversed(transcript):
        if entry["role"] == "assistant":
            latest_assistant = entry["text"]
            break

    for _ in range(5):
        candidate = random.choice(prompts)
        if candidate not in latest_assistant:
            return candidate
    return random.choice(prompts)


def detect_rulebased_issue(text: str) -> tuple[str, str] | None:
    for pattern, correction_template, reason in RULEBASE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        groups = match.groupdict()
        correction = correction_template.format(**groups)
        return correction, reason
    return None


TOPIC_DISPLAY_NAME: dict[str, str] = {
    "arbeit": "Arbeit",
    "lernen": "Deutschlernen",
    "familie": "Familie",
    "sport": "Sport",
    "essen": "Essen",
    "reise": "Reisen",
    "konflikt": "Konfliktsituationen",
    "freizeit": "Freizeit",
}


def update_learner_profile_from_user_turn(user_text: str) -> None:
    topic = detect_topic(user_text)
    issue = detect_rulebased_issue(user_text)
    correction_key = issue[0][:120] if issue else ""

    with PROFILE_LOCK:
        LEARNER_PROFILE["total_user_messages"] += 1
        LEARNER_PROFILE["last_updated"] = utc_now_iso()
        if topic:
            current = LEARNER_PROFILE["topic_counts"].get(topic, 0)
            LEARNER_PROFILE["topic_counts"][topic] = current + 1
        if correction_key:
            current = LEARNER_PROFILE["common_corrections"].get(correction_key, 0)
            LEARNER_PROFILE["common_corrections"][correction_key] = current + 1


def learner_memory_system_note() -> str:
    with PROFILE_LOCK:
        total_messages = LEARNER_PROFILE["total_user_messages"]
        topic_counts = sorted(
            LEARNER_PROFILE["topic_counts"].items(),
            key=lambda item: item[1],
            reverse=True,
        )[:3]
        correction_counts = sorted(
            LEARNER_PROFILE["common_corrections"].items(),
            key=lambda item: item[1],
            reverse=True,
        )[:3]

    if total_messages < 3 and not topic_counts and not correction_counts:
        return ""

    parts: list[str] = [
        "Langzeitprofil des Lernenden (aus frueheren Gespraechen):",
        f"- Anzahl gespeicherter Nutzerbeitraege: {total_messages}",
    ]
    if topic_counts:
        topic_names = [TOPIC_DISPLAY_NAME.get(topic, topic) for topic, _ in topic_counts]
        parts.append(f"- Haeufige Themen: {', '.join(topic_names)}.")
    if correction_counts:
        corrections = [corr for corr, _ in correction_counts]
        parts.append("- Haeufige Korrekturziele: " + " | ".join(corrections))
    parts.append(
        "- Nutze das Profil nur, wenn es zum aktuellen Turn passt. Prioritaet hat immer die aktuelle Nachricht."
    )
    return "\n".join(parts)


def should_offer_micro_correction(turn_count: int, has_issue: bool) -> bool:
    if not has_issue:
        return False
    return turn_count <= 2 or turn_count % 3 == 0


def target_reply_sentence_limit(constraints: ChatReplyConstraints) -> int:
    return constraints.sentence_count if constraints.sentence_count in {1, 2, 3} else 2


def target_reply_word_limit(constraints: ChatReplyConstraints) -> int:
    sentence_limit = target_reply_sentence_limit(constraints)
    if constraints.concise:
        concise_limits = {1: 16, 2: 24, 3: 30} if constraints.simple_german else {1: 20, 2: 28, 3: 36}
        return min(CHAT_REPLY_MAX_WORDS, concise_limits.get(sentence_limit, 28))
    if constraints.simple_german:
        simple_limits = {1: 20, 2: 30, 3: 42}
        return min(CHAT_REPLY_MAX_WORDS, simple_limits.get(sentence_limit, 30))
    default_limits = {1: 28, 2: CHAT_REPLY_MAX_WORDS, 3: min(CHAT_REPLY_MAX_WORDS, 54)}
    return min(CHAT_REPLY_MAX_WORDS, default_limits.get(sentence_limit, CHAT_REPLY_MAX_WORDS))


def strip_leading_chat_filler(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return cleaned
    original = cleaned
    for pattern in LEADING_FILLER_PATTERNS:
        cleaned = pattern.sub("", cleaned, count=1).strip()
    return cleaned or original


def split_reply_sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if item.strip()]


def expand_reply_sentence_clauses(sentences: list[str]) -> list[str]:
    expanded: list[str] = []
    for sentence in sentences:
        pieces = [piece.strip().rstrip(",;:") for piece in CLAUSE_BREAK_PATTERN.split(sentence) if piece.strip()]
        if len(pieces) <= 1:
            expanded.append(sentence.strip())
            continue
        for piece in pieces:
            normalized_piece = piece[:1].upper() + piece[1:] if piece else piece
            if normalized_piece and normalized_piece[-1] not in ".!?":
                normalized_piece += "."
            expanded.append(normalized_piece)
    return [item for item in expanded if item]


def build_quick_reply_tail(constraints: ChatReplyConstraints, level: str) -> list[str]:
    if not constraints.sentence_count or constraints.sentence_count <= 1:
        return []
    effective_level = apply_simple_german_level(level, constraints)
    if constraints.simple_german or effective_level in {"A1", "A2"}:
        bank = ["Wir koennen direkt weiterreden.", "Ich spreche hier nur Deutsch."]
    else:
        bank = ["Wir koennen direkt weiterreden.", "Ich spreche hier mit dir auf Deutsch."]
    return bank[: max(0, constraints.sentence_count - 1)]


def parse_simple_math_number(raw: str) -> float | None:
    text = str(raw or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def format_simple_math_number(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return str(int(rounded))
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def build_simple_math_answer(
    segment: str,
    level: str,
    constraints: ChatReplyConstraints | None = None,
) -> str | None:
    constraints = constraints or ChatReplyConstraints()
    effective_level = apply_simple_german_level(level, constraints)
    lowered = normalize_for_matching(segment.strip())
    match = SIMPLE_ARITHMETIC_PATTERN.match(lowered)
    if match:
        left = parse_simple_math_number(match.group("a"))
        right = parse_simple_math_number(match.group("b"))
        operator = str(match.group("op") or "").lower().strip()
        if left is None or right is None:
            return None
        if operator in {"/", ":", "geteilt durch"} and abs(right) <= 1e-9:
            return "Durch null kann ich nicht teilen."
        if operator in {"+", "plus"}:
            result = left + right
            label = "plus"
        elif operator in {"-", "minus"}:
            result = left - right
            label = "minus"
        elif operator in {"*", "x", "×", "mal"}:
            result = left * right
            label = "mal"
        elif operator in {"/", ":", "geteilt durch"}:
            result = left / right
            label = "geteilt durch"
        else:
            return None
        return (
            f"{format_simple_math_number(left)} {label} {format_simple_math_number(right)} "
            f"ist {format_simple_math_number(result)}."
        )

    if MATH_CAPABILITY_PATTERN.search(lowered):
        if effective_level in {"A1", "A2"}:
            return "Ja, ich kann einfache Mathe machen. Schreib mir die Aufgabe."
        return "Ja, ich kann einfache Matheaufgaben direkt loesen. Schreib mir einfach die Rechnung."

    return None


def is_basic_direct_question(user_text: str) -> bool:
    normalized = normalize_for_matching(str(user_text or "").strip())
    if not normalized:
        return False
    if SIMPLE_ARITHMETIC_PATTERN.match(normalized):
        return True
    if MATH_CAPABILITY_PATTERN.search(normalized):
        return True
    question_segments = extract_question_segments(user_text)
    if len(question_segments) > 1:
        return True
    return bool(question_segments and len(GERMAN_TOKEN_RE.findall(normalized)) <= 8)


def build_known_question_answer(
    segment: str,
    level: str,
    constraints: ChatReplyConstraints | None = None,
    coherence: SessionCoherenceDict | None = None,
) -> str | None:
    constraints = constraints or ChatReplyConstraints()
    effective_level = apply_simple_german_level(level, constraints)
    assistant_facts = dict((coherence or {}).get("assistant_facts") or {})
    lowered = normalize_for_matching(segment.strip())
    date_label, time_label = german_now_labels()
    asks_time = bool(TIME_QUESTION_PATTERN.search(lowered))
    asks_date = bool(DATE_QUESTION_PATTERN.search(lowered))
    asks_day = bool(DAY_QUESTION_PATTERN.search(lowered))
    asks_day_or_date = asks_date or asks_day

    math_answer = build_simple_math_answer(segment, effective_level, constraints)
    if math_answer:
        return math_answer

    if HOW_ARE_YOU_PATTERN.search(lowered):
        return "Mir geht es gut, danke." if effective_level in {"A1", "A2"} else "Mir geht's gut, danke."

    if NAME_QUESTION_PATTERN.search(lowered):
        if assistant_facts.get("identity_summary"):
            return str(assistant_facts["identity_summary"])
        if effective_level in {"A1", "A2"}:
            return "Ich bin dein deutscher Tutor."
        return "Ich bin dein deutscher Gespraechspartner zum Ueben."

    if asks_time and asks_day_or_date:
        return f"Heute ist {date_label}, und es ist gerade {time_label} Uhr."

    if asks_time:
        return f"Es ist gerade {time_label} Uhr."

    if asks_date:
        return f"Heute ist {date_label}."

    if asks_day:
        weekday = date_label.split(",")[0]
        return f"Heute ist {weekday}."

    if FAVORITE_COLOR_PATTERN.search(lowered):
        if effective_level in {"A1", "A2"}:
            return "Meine Lieblingsfarbe ist Blau."
        return "Ich mag am liebsten Dunkelblau."

    if AGE_QUESTION_PATTERN.search(lowered):
        if assistant_facts.get("age_summary"):
            return str(assistant_facts["age_summary"])
        if effective_level in {"A1", "A2"}:
            return "Ich habe kein echtes Alter."
        return "Ich habe als digitaler Sprachpartner kein echtes Alter."

    if FROM_WHERE_PATTERN.search(lowered):
        if assistant_facts.get("origin_summary"):
            return str(assistant_facts["origin_summary"])
        if effective_level in {"A1", "A2"}:
            return "Ich bin digital und komme nicht aus einer Stadt."
        return "Ich lebe nicht an einem festen Ort, weil ich digital bin."

    return None


def maybe_direct_question_bundle_reply(
    text: str,
    level: str,
    constraints: ChatReplyConstraints | None = None,
    coherence: SessionCoherenceDict | None = None,
) -> str | None:
    constraints = constraints or ChatReplyConstraints()
    question_segments = extract_question_segments(text)
    if not question_segments:
        return None

    ordered_answers: list[str] = []
    seen_answers: set[str] = set()
    for segment in question_segments:
        answer = build_known_question_answer(segment, level, constraints, coherence=coherence)
        if not answer:
            continue
        answer_key = normalize_for_matching(answer)
        if answer_key in seen_answers:
            continue
        ordered_answers.append(answer)
        seen_answers.add(answer_key)

    if not ordered_answers:
        return None

    sentence_limit = target_reply_sentence_limit(constraints)
    if constraints.sentence_count and len(ordered_answers) < sentence_limit:
        ordered_answers.extend(build_quick_reply_tail(constraints, level))
    return " ".join(ordered_answers[:sentence_limit]).strip()


def maybe_smalltalk_reply(
    text: str,
    level: str,
    constraints: ChatReplyConstraints | None = None,
    coherence: SessionCoherenceDict | None = None,
) -> str | None:
    constraints = constraints or ChatReplyConstraints()
    effective_level = apply_simple_german_level(level, constraints)
    assistant_facts = dict((coherence or {}).get("assistant_facts") or {})
    lowered = normalize_for_matching(text.strip())

    if HOW_ARE_YOU_PATTERN.search(lowered):
        if "mir geht" in lowered:
            lead = "Mir geht es auch gut." if effective_level in {"A1", "A2"} else "Mir geht's auch gut, danke."
            tail = ["Und dir?"] if target_reply_sentence_limit(constraints) >= 2 else []
            return " ".join([lead, *tail]).strip()
        if effective_level in {"A1", "A2"}:
            lead = "Mir geht es gut, danke."
        else:
            lead = "Mir geht's gut, danke."
        tail = ["Und dir?"] if target_reply_sentence_limit(constraints) >= 2 else []
        return " ".join([lead, *tail]).strip()

    if NAME_QUESTION_PATTERN.search(lowered):
        lead = str(
            assistant_facts.get(
                "identity_summary",
                (
                    "Ich bin dein deutscher Gespraechspartner zum Ueben."
                    if effective_level not in {"A1", "A2"}
                    else "Ich bin dein deutscher Tutor zum Ueben."
                ),
            )
        )
        return " ".join([lead, *build_quick_reply_tail(constraints, effective_level)]).strip()

    if GREETING_ONLY_PATTERN.match(lowered):
        lead = "Hallo!" if constraints.concise else (
            "Hallo! Schoen, dass du da bist." if effective_level in {"A1", "A2"} else "Hallo! Schoen, dich zu hoeren."
        )
        return " ".join([lead, *build_quick_reply_tail(constraints, effective_level)]).strip()

    words = GERMAN_TOKEN_RE.findall(lowered)
    if words and len(words) <= 6 and THANKS_PATTERN.search(lowered):
        lead = "Gern."
        if target_reply_sentence_limit(constraints) >= 2:
            return " ".join([lead, "Wir koennen direkt weiterreden."]).strip()
        return lead

    return None


def maybe_personal_answer(
    text: str,
    level: str,
    constraints: ChatReplyConstraints | None = None,
    coherence: SessionCoherenceDict | None = None,
) -> str | None:
    constraints = constraints or ChatReplyConstraints()
    effective_level = apply_simple_german_level(level, constraints)
    assistant_facts = dict((coherence or {}).get("assistant_facts") or {})
    lowered = normalize_for_matching(text.strip())
    date_label, time_label = german_now_labels()
    asks_time = bool(TIME_QUESTION_PATTERN.search(lowered))
    asks_date = bool(DATE_QUESTION_PATTERN.search(lowered))
    asks_day = bool(DAY_QUESTION_PATTERN.search(lowered))
    asks_day_or_date = asks_date or asks_day

    if asks_time and asks_day_or_date:
        return f"Heute ist {date_label}, und es ist gerade {time_label} Uhr."

    if asks_time:
        return f"Es ist gerade {time_label} Uhr."

    if asks_date:
        return f"Heute ist {date_label}."

    if asks_day:
        weekday = date_label.split(",")[0]
        return f"Heute ist {weekday}."

    if FAVORITE_COLOR_PATTERN.search(lowered):
        if effective_level in {"A1", "A2"}:
            return "Meine Lieblingsfarbe ist Blau."
        return "Ich mag am liebsten Dunkelblau, weil es ruhig wirkt."

    if AGE_QUESTION_PATTERN.search(lowered):
        if assistant_facts.get("age_summary"):
            return str(assistant_facts["age_summary"])
        if effective_level in {"A1", "A2"}:
            return "Ich habe kein echtes Alter."
        return "Ich habe als digitaler Sprachpartner kein echtes Alter."

    if FROM_WHERE_PATTERN.search(lowered):
        if assistant_facts.get("origin_summary"):
            return str(assistant_facts["origin_summary"])
        if effective_level in {"A1", "A2"}:
            return "Ich komme nicht aus einer Stadt. Ich bin digital."
        return "Ich lebe nicht an einem festen Ort, weil ich digital bin."

    return None


def rulebased_reply(
    user_text: str,
    level: str,
    transcript: list[TranscriptEntryDict],
    constraints: ChatReplyConstraints | None = None,
    coherence: SessionCoherenceDict | None = None,
) -> str:
    constraints = constraints or extract_chat_reply_constraints(user_text)
    effective_level = apply_simple_german_level(level, constraints)
    text = user_text.strip()
    words = GERMAN_TOKEN_RE.findall(text)
    user_is_question = text.endswith("?") or bool(
        re.match(
            r"^\s*(wer|wie|was|wo|wann|warum|wieso|weshalb|welche|welcher|welches|kann|kannst|koennen|hast|haben|habt|bist|ist|sind)\b",
            text,
            flags=re.IGNORECASE,
        )
    )
    turn_count = len([entry for entry in transcript if entry["role"] == "user"])
    topic = detect_topic(text)
    ask = rulebased_followup(level=effective_level, topic=topic, transcript=transcript)
    reflection = build_topic_reflection(topic)
    emotion_feedback = detect_emotion_feedback(text)

    if SPANISH_HINT_PATTERN.search(text):
        return restore_german_text(
            (
            "Wir bleiben bei Deutsch, ganz entspannt. "
            "Sag denselben Gedanken bitte auf Deutsch. "
              f"{ask}"
              )
        )

    direct_question_bundle = maybe_direct_question_bundle_reply(
        text=text,
        level=effective_level,
        constraints=constraints,
        coherence=coherence,
    )
    if direct_question_bundle:
        return restore_german_text(direct_question_bundle)

    smalltalk = maybe_smalltalk_reply(
        text=text,
        level=effective_level,
        constraints=constraints,
        coherence=coherence,
    )
    if smalltalk:
        return restore_german_text(smalltalk)

    personal_answer = maybe_personal_answer(
        text=text,
        level=effective_level,
        constraints=constraints,
        coherence=coherence,
    )
    if personal_answer:
        return restore_german_text(personal_answer)

    if len(words) < 2:
        return restore_german_text("Ich bin da und hoere zu.")

    parts: list[str] = []
    if emotion_feedback:
        parts.append(emotion_feedback)

    if not user_is_question:
        parts.append(reflection)
    elif topic and not constraints.concise:
        parts.append(build_topic_reflection(topic))

    should_add_followup = (
        (not constraints.concise)
        and (not user_is_question)
        and len(words) >= 7
        and turn_count % 3 == 1
    )
    if should_add_followup:
        parts.append(ask)
    if not parts:
        if user_is_question:
            parts.append(
                "Ich brauche hier eine genauere Frage."
                if effective_level in {"A1", "A2"}
                else "Ich brauche hier etwas mehr Kontext, um direkt zu antworten."
            )
        else:
            parts.append("Ich hoere zu.")
    return restore_german_text(" ".join(part.strip() for part in parts if part).strip())


def finalize_assistant_reply(text: str, constraints: ChatReplyConstraints | None = None) -> str:
    constraints = constraints or ChatReplyConstraints()
    cleaned = " ".join(strip_leading_chat_filler(text).strip().split())
    if not cleaned:
        return cleaned

    sentences = split_reply_sentences(cleaned)
    sentence_limit = target_reply_sentence_limit(constraints)
    if constraints.sentence_count and len(sentences) < sentence_limit:
        expanded_sentences = expand_reply_sentence_clauses(sentences)
        if len(expanded_sentences) > len(sentences):
            sentences = expanded_sentences
            cleaned = " ".join(sentences).strip()
    if len(sentences) > sentence_limit:
        cleaned = " ".join(sentences[:sentence_limit]).strip()

    words = cleaned.split()
    word_limit = target_reply_word_limit(constraints)
    if len(words) > word_limit:
        cleaned = " ".join(words[:word_limit]).rstrip(",;:")
        if cleaned and cleaned[-1] not in ".!?":
            cleaned += "."

    if cleaned and cleaned[-1] not in ".!?":
        last_punct = max(cleaned.rfind("."), cleaned.rfind("?"), cleaned.rfind("!"))
        if last_punct >= 15:
            cleaned = cleaned[: last_punct + 1].strip()
        elif sentence_limit <= 1 or constraints.concise:
            cleaned = cleaned.rstrip(",;:") + "."
    return cleaned


def split_complete_assistant_sentences(text: str, constraints: ChatReplyConstraints | None = None) -> list[str]:
    finalized = finalize_assistant_reply(text, constraints=constraints)
    if not finalized:
        return []
    sentences = split_reply_sentences(finalized)
    return [item for item in sentences if item and item[-1] in ".!?"]


def detect_assistant_reply_issue(reply: str, user_text: str) -> str | None:
    normalized_reply = normalize_for_matching(reply)
    normalized_user = normalize_for_matching(user_text)
    if not normalized_reply:
        return "empty"
    if normalized_reply == normalized_user:
        return "echoed_user"
    if any(tag in reply for tag in ("<role>", "<regeln>", "<task_data>")):
        return "prompt_leak"
    if re.search(r"(^|\n)\s*(?:[-*•]|\d+\.)\s", reply):
        return "list_format"
    meta_markers = [
        "as an ai",
        "language model",
        "als ki",
        "als ai",
        "ich bin nur ein",
        "i cannot",
        "no puedo",
        "sag noch einen kurzen punkt dazu",
        "erzaehl mir noch einen kurzen punkt dazu",
    ]
    if any(marker in normalized_reply for marker in meta_markers):
        return "meta_talk"
    if is_basic_direct_question(user_text) and (
        "das haengt von der situation ab" in normalized_reply
        or "das kommt auf die situation an" in normalized_reply
    ):
        return "vague_direct_answer"
    sentences = [normalize_for_matching(item) for item in re.split(r"(?<=[.!?])\s+", reply) if item.strip()]
    if len(sentences) >= 2 and len(set(sentences)) <= max(1, len(sentences) // 2):
        return "repetition"
    return None


def find_rulebased_issues(user_turns: list[str]) -> list[tuple[str, str, str]]:
    issues: list[tuple[str, str, str]] = []
    for turn in user_turns:
        issue = detect_rulebased_issue(turn)
        if not issue:
            continue
        correction, reason = issue
        issues.append((turn, correction, reason))
    return issues[:8]


def rulebased_feedback(transcript: list[TranscriptEntryDict], level: str) -> str:
    user_turns = [entry["text"] for entry in transcript if entry["role"] == "user"]
    if not user_turns:
        return (
            "1) Resumen\nNo hay frases del alumno para analizar.\n\n"
            "2) Errores\nNo evaluable.\n\n"
            "3) Pronunciacion\nNo evaluable.\n\n"
            "4) Plan\nEmpieza una conversacion y vuelve a pulsar Acabar conversacion."
        )

    issues = find_rulebased_issues(user_turns)
    short_turns = sum(1 for t in user_turns if len(t.split()) < 5)
    long_turns = len(user_turns) - short_turns
    summary: list[str] = [
        "1) Resumen de rendimiento",
        f"- Nivel objetivo: {level}",
        f"- Intervenciones del alumno: {len(user_turns)}",
        f"- Frases cortas (<5 palabras): {short_turns}",
        f"- Frases mas desarrolladas: {long_turns}",
        "",
        "2) Errores detectados",
    ]

    if issues:
        for idx, (original, correction, reason) in enumerate(issues, start=1):
            summary.append(f"{idx}. Original: {original}")
            summary.append(f"   Correccion: {correction}")
            summary.append(f"   Motivo: {reason}")
    else:
        summary.append("No se detectaron errores recurrentes por patrones.")
        summary.append("Pistas a revisar: orden del verbo, genero/articulos, casos (Akk/Dat).")

    summary.extend(
        [
            "",
            "3) Pronunciacion y fluidez",
            "- Practica ritmo: pausas cortas entre grupos de palabras.",
            "- Repite vocales largas/cortas: ie vs i, u vs ue.",
            "- Entrena sonidos: ch, r, o umlaut (oe).",
            "",
            "4) Que repasar (plan corto)",
            "1. Verbos en segunda posicion en frases principales.",
            "2. Preguntas W- y preguntas de si/no.",
            "3. Artikeln der/die/das en contexto.",
            "4. Perfekt para hablar del dia.",
            "5. Conectores: weil, deshalb, obwohl.",
            "",
            "5) Frases de practica (repite en voz alta)",
        ]
    )

    practice_bank = [issue[1] for issue in issues] or [
        "Heute habe ich viel zu tun, aber ich bleibe ruhig.",
        "Am Wochenende mochte ich mit Freunden Deutsch sprechen.",
        "Ich lerne jeden Tag 20 Minuten, damit ich flussiger werde.",
    ]
    for idx, sentence in enumerate(practice_bank[:5], start=1):
        summary.append(f"{idx}. {sentence}")

    return "\n".join(summary)


CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
CEFR_RANK = {level: idx for idx, level in enumerate(CEFR_LEVELS)}


def clamp_cefr_rank(rank: int) -> int:
    return max(0, min(rank, len(CEFR_LEVELS) - 1))


def estimate_level_from_text(text: str, declared_level: str) -> str:
    normalized = normalize_for_matching(text)
    words = GERMAN_TOKEN_RE.findall(normalized)
    word_count = len(words)
    sentence_count = max(1, len(re.findall(r"[.!?]", text)))
    long_words = sum(1 for word in words if len(word) >= 8)
    connector_hits = sum(
        1
        for marker in ["obwohl", "waehrend", "deshalb", "deswegen", "trotzdem", "sodass", "damit", "weil", "denn"]
        if marker in normalized
    )

    if word_count < 14:
        rank = 0
    elif word_count < 28:
        rank = 1
    elif word_count < 55:
        rank = 2
    elif word_count < 95:
        rank = 3
    else:
        rank = 4

    if connector_hits >= 3:
        rank += 1
    if long_words >= 10 and sentence_count >= 4:
        rank += 1

    declared_rank = CEFR_RANK.get(declared_level, CEFR_RANK[DEFAULT_LEVEL])
    # Keep estimation close to selected level to avoid extreme jumps in short samples.
    rank = max(declared_rank - 1, min(rank, declared_rank + 1))
    return CEFR_LEVELS[clamp_cefr_rank(rank)]


QUESTION_START_RE = re.compile(
    r"^\s*(wer|wie|was|wo|wann|warum|wieso|weshalb|welche|welcher|welches|"
    r"kann|kannst|koennen|hast|haben|habt|bist|ist|sind|willst|moechtest)\b",
    flags=re.IGNORECASE,
)
QUESTION_PHRASE_PATTERNS = [
    re.compile(r"\bwas soll ich\b", flags=re.IGNORECASE),
    re.compile(r"\bwie kann ich\b", flags=re.IGNORECASE),
    re.compile(r"\bwas kann ich\b", flags=re.IGNORECASE),
    re.compile(r"\bkannst du\b", flags=re.IGNORECASE),
    re.compile(r"\bhast du\b", flags=re.IGNORECASE),
    re.compile(r"\bwie spaet ist es\b", flags=re.IGNORECASE),
]
SUBORDINATE_CONNECTORS = {
    "weil",
    "dass",
    "wenn",
    "obwohl",
    "waehrend",
    "damit",
    "sodass",
    "bevor",
    "nachdem",
}
FILLER_WORDS = {"aeh", "eh", "hm", "also", "naja", "halt"}


def split_text_segments(text: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"[.!?]+", text) if part.strip()]
    return parts


def sentence_looks_like_question(text: str) -> bool:
    if QUESTION_START_RE.match(text):
        return True
    lowered = normalize_for_matching(text)
    return any(pattern.search(lowered) for pattern in QUESTION_PHRASE_PATTERNS)


def ensure_subordinate_commas(sentence: str) -> str:
    words = sentence.split()
    if len(words) < 4:
        return sentence
    out: list[str] = []
    for idx, word in enumerate(words):
        token = normalize_for_matching(re.sub(r"[^\wÄÖÜäöüß']", "", word))
        if token in SUBORDINATE_CONNECTORS and idx >= 2 and out:
            if not out[-1].endswith(","):
                out[-1] = out[-1].rstrip(",") + ","
        out.append(word)
    return " ".join(out).replace(" ,", ",")


def autopunctuate_monologue_text(text: str) -> str:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return ""
    cleaned = restore_german_text(cleaned)

    if re.search(r"[.!?]", cleaned):
        normalized = re.sub(r"\s*([.!?])\s*", r"\1 ", cleaned).strip()
        normalized = re.sub(r"\s+,", ",", normalized)
        normalized = re.sub(r"\s{2,}", " ", normalized)
        parts = split_text_segments(normalized)
        rebuilt: list[str] = []
        cursor = 0
        for part in parts:
            idx = normalized.find(part, cursor)
            end = idx + len(part) if idx >= 0 else cursor + len(part)
            punctuation = "."
            for pos in range(end, min(len(normalized), end + 3)):
                if normalized[pos] in ".!?":
                    punctuation = normalized[pos]
                    break
            sentence = ensure_subordinate_commas(part)
            sentence = sentence[0].upper() + sentence[1:] if sentence else sentence
            rebuilt.append(sentence.rstrip(".!?") + punctuation)
            cursor = end + 1
        return " ".join(rebuilt).strip()

    words = cleaned.split()
    sentences: list[str] = []
    current: list[str] = []
    for word in words:
        current.append(word)
        normalized_word = normalize_for_matching(re.sub(r"[^\wÄÖÜäöüß']", "", word))
        if len(current) >= 20:
            sentences.append(" ".join(current))
            current = []
            continue
        if len(current) >= 14 and normalized_word in {"und", "aber", "deshalb", "danach", "trotzdem"}:
            sentences.append(" ".join(current[:-1]))
            current = [word]

    if current:
        sentences.append(" ".join(current))

    final_sentences: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip(" ,;:")
        if not sentence:
            continue
        sentence = ensure_subordinate_commas(sentence)
        sentence = sentence[0].upper() + sentence[1:] if sentence else sentence
        punctuation = "?" if sentence_looks_like_question(sentence) else "."
        final_sentences.append(sentence.rstrip(".!?") + punctuation)

    return " ".join(final_sentences).strip()


def snippet_around(text: str, start: int, end: int, radius: int = 30) -> str:
    s = max(0, start - radius)
    e = min(len(text), end + radius)
    snippet = text[s:e].strip()
    return snippet or text[:120]


def detect_monologue_issues(raw_text: str, normalized_text: str) -> list[tuple[str, str, str]]:
    issues: list[tuple[str, str, str]] = []
    text = " ".join(raw_text.strip().split())
    if not text:
        return issues

    words = GERMAN_TOKEN_RE.findall(text)
    punctuation_marks = re.findall(r"[.!?]", text)
    commas = re.findall(r",", text)

    if len(words) >= 10 and not punctuation_marks:
        issues.append(
            (
                text[:220],
                normalized_text,
                "Puntuacion: el monologo viene seguido, sin finales de frase claros ni pausas marcadas.",
            )
        )

    if len(words) >= 14 and len(commas) == 0:
        issues.append(
            (
                text[:220],
                ensure_subordinate_commas(normalized_text),
                "Puntuacion: faltan comas para separar bloques y subordinadas.",
            )
        )

    segments = split_text_segments(normalized_text) if re.search(r"[.!?]", normalized_text) else [normalized_text]
    for segment in segments:
        seg = segment.strip()
        if not seg:
            continue
        if sentence_looks_like_question(seg) and not seg.endswith("?"):
            issues.append(
                (
                    seg,
                    seg.rstrip(".!") + "?",
                    "Puntuacion: esta frase es interrogativa y debe cerrar con signo de pregunta.",
                )
            )

    lowered_original = normalize_for_matching(text)
    if "?" not in text and any(pattern.search(lowered_original) for pattern in QUESTION_PHRASE_PATTERNS):
        question_like = next(
            (pattern.pattern.replace("\\b", "") for pattern in QUESTION_PHRASE_PATTERNS if pattern.search(lowered_original)),
            "pregunta",
        )
        issues.append(
            (
                text[:220],
                normalized_text if "?" in normalized_text else normalized_text.rstrip(".!") + "?",
                f"Puntuacion: se detecta estructura interrogativa ({question_like}) sin signo de pregunta.",
            )
        )

    if text and text[0].islower():
        issues.append(
            (
                text[:120],
                text[0].upper() + text[1:],
                "Ortografia: la frase inicial debe empezar con mayuscula.",
            )
        )

    filler_hits = [token for token in GERMAN_TOKEN_RE.findall(normalize_for_matching(text)) if token in FILLER_WORDS]
    if len(filler_hits) >= 3:
        issues.append(
            (
                text[:220],
                normalized_text,
                "Fluidez: hay demasiadas muletillas; intenta pausas breves y frases mas limpias.",
            )
        )

    # Reuse existing rule-based grammar patterns on each sentence.
    for segment in segments:
        issue = detect_rulebased_issue(segment)
        if not issue:
            continue
        correction, reason = issue
        issues.append((segment, correction, f"Gramatica: {reason}"))

    # Detect likely subordinate-clause comma omissions in original text.
    lowered = normalize_for_matching(text)
    for connector in sorted(SUBORDINATE_CONNECTORS):
        for match in re.finditer(rf"\b{re.escape(connector)}\b", lowered):
            idx = match.start()
            if idx == 0:
                continue
            prev_chunk = lowered[max(0, idx - 20) : idx].rstrip()
            if prev_chunk.endswith(","):
                continue
            original_snippet = snippet_around(text, idx, idx + len(connector))
            corrected = re.sub(
                rf"\s+({re.escape(connector)})\b",
                r", \1",
                original_snippet,
                count=1,
                flags=re.IGNORECASE,
            )
            if corrected != original_snippet:
                issues.append(
                    (
                        original_snippet,
                        corrected,
                        "Puntuacion/Gramatica: antes de subordinadas con este conector suele ir coma.",
                    )
                )

    deduped: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for original, correction, reason in issues:
        key = (
            normalize_for_matching(original.strip()),
            normalize_for_matching(correction.strip()),
            normalize_for_matching(reason.strip()),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append((original.strip(), correction.strip(), reason.strip()))
    return deduped


def build_monologue_heuristic_notes(raw_text: str, normalized_text: str, issues: list[tuple[str, str, str]]) -> str:
    words = GERMAN_TOKEN_RE.findall(raw_text)
    marks = re.findall(r"[.!?]", raw_text)
    lines = [
        f"- Palabras detectadas: {len(words)}",
        f"- Signos de final de frase en texto original: {len(marks)}",
        f"- Errores heuristicas detectados: {len(issues)}",
        "- Si faltan signos o comas, priorizar su correccion.",
    ]
    for idx, (original, correction, reason) in enumerate(issues[:8], start=1):
        lines.append(f"{idx}) {reason}")
        lines.append(f"   Original: {original}")
        lines.append(f"   Correccion sugerida: {correction}")
    if len(issues) > 8:
        lines.append(f"- ... y {len(issues) - 8} observaciones adicionales.")
    lines.append(f"- Version auto-segmentada base: {normalized_text}")
    return "\n".join(lines)


def study_focus_for_goal(estimated_level: str, goal_level: str) -> list[str]:
    gap = CEFR_RANK.get(goal_level, 0) - CEFR_RANK.get(estimated_level, 0)
    if gap <= 0:
        return [
            "Consolidar precision gramatical en habla espontanea.",
            "Reducir pausas y muletillas con shadowing 10 min/dia.",
            "Ampliar vocabulario tematico (trabajo, sociedad, opinion).",
            "Practicar monologos de 2-3 minutos con cronometro.",
            "Autoevaluacion semanal grabandote y corrigiendo 5 errores.",
        ]
    if gap == 1:
        return [
            "Conectores para argumentar: obwohl, waehrend, trotzdem, deshalb.",
            "Oraciones subordinadas con verbo final de forma estable.",
            "Vocabulario abstracto para opinion y matices.",
            "Monologos de 3 minutos con estructura: idea, ejemplo, conclusion.",
            "Correccion activa de 5 errores frecuentes despues de cada sesion.",
        ]
    return [
        "Base gramatical solida: orden verbal en Hauptsatz/Nebensatz.",
        "Pronombres, casos (Akk/Dat) y articulos en contexto real.",
        "Bloques diarios: 10 min escucha + 10 min habla + 10 min correccion.",
        "Monologos guiados por tema con feedback y reintento inmediato.",
        "Repeticion espaciada de frases utiles para fluidez automatica.",
    ]


def rulebased_monologue_feedback(text: str, level: str, goal_level: str, estimated_level: str) -> str:
    improved = autopunctuate_monologue_text(text)
    issues = detect_monologue_issues(raw_text=text, normalized_text=improved)
    focus_items = study_focus_for_goal(estimated_level=estimated_level, goal_level=goal_level)

    lines: list[str] = [
        "1) Diagnostico breve",
        f"- Nivel declarado: {level}",
        f"- Nivel estimado: {estimated_level}",
        f"- Goal objetivo: {goal_level}",
        f"- Fallos detectados: {len(issues)}",
        "- Comentario: se observa margen de mejora en precision y fluidez para acercarte al objetivo.",
        "",
        "2) Errores clave",
    ]
    if issues:
        for idx, (original, correction, reason) in enumerate(issues[:12], start=1):
            lines.append(f"{idx}. Original: {original}")
            lines.append(f"   Correccion: {correction}")
            lines.append(f"   Explicacion: {reason}")
    else:
        lines.append("1. No se detectaron errores claros por heuristicas, pero revisa igualmente naturalidad y variedad.")
        lines.append("   Recomendacion: mejora conectores, orden del verbo y precision de articulos/casos.")

    lines.extend(
        [
            "",
            "3) Version mejorada del monologo",
            improved or "(No se pudo reconstruir una version mejorada.)",
            "",
            "4) Pronunciacion y fluidez",
            "- Entrena vocales largas/cortas y ritmo por grupos de palabras.",
            "- Practica sonidos conflictivos: ch, r, oe/ue/ae.",
            "- Repite 3 veces cada frase clave antes de pasar al siguiente bloque.",
            "",
            "5) Brecha hasta el nivel objetivo",
            f"- Distancia estimada: {max(0, CEFR_RANK.get(goal_level, 0) - CEFR_RANK.get(estimated_level, 0))} nivel(es).",
            "- Clave: mas precision gramatical + mas variedad de conectores + mas automatizacion oral.",
            "",
            "6) Plan de estudio (2 semanas)",
        ]
    )
    for idx, item in enumerate(focus_items, start=1):
        lines.append(f"{idx}. {item}")

    return "\n".join(lines)


EXAM_DISPLAY_NAMES: dict[ExamName, str] = {
    "goethe": "Goethe-Zertifikat",
    "telc": "telc Deutsch",
    "testdaf": "TestDaF",
}

EXAM_SECTION_NAMES: dict[ExamSection, str] = {
    "sprechen": "Sprechen",
    "hoeren": "Horen",
    "lesen": "Lesen",
    "schreiben": "Schreiben",
    "grammatik": "Grammatik",
    "wortschatz": "Wortschatz",
    "verben": "Verben",
}

EXAM_OFFICIAL_BASIS: dict[ExamName, str] = {
    "goethe": (
        "Inspirado en la estructura oficial modular del Goethe-Institut "
        "(Lesen, Horen, Schreiben, Sprechen)."
    ),
    "telc": (
        "Inspirado en los formatos oficiales telc Deutsch; en varios niveles incluye "
        "componentes tipo Sprachbausteine."
    ),
    "testdaf": (
        "Inspirado en la estructura oficial TestDaF (Leseverstehen, Horverstehen, "
        "Schriftlicher Ausdruck, Mundlicher Ausdruck)."
    ),
}

CEFR_CAN_DO: dict[str, dict[str, str]] = {
    "A1": {
        "sprechen": "puedes presentarte, responder preguntas personales y hablar en frases muy breves.",
        "hoeren": "puedes entender palabras y expresiones muy frecuentes si se habla despacio.",
        "lesen": "puedes entender anuncios y textos muy cortos con vocabulario cotidiano.",
        "schreiben": "puedes escribir frases simples sobre datos personales y rutina.",
    },
    "A2": {
        "sprechen": "puedes describir rutina, gustos y planes simples con frases conectadas.",
        "hoeren": "puedes captar informacion esencial en situaciones cotidianas claras.",
        "lesen": "puedes leer textos breves de vida diaria y localizar informacion concreta.",
        "schreiben": "puedes escribir mensajes y textos cortos sobre experiencias simples.",
    },
    "B1": {
        "sprechen": "puedes desenvolverte en viajes y explicar opiniones sencillas con razones.",
        "hoeren": "puedes seguir ideas principales de conversaciones y audios claros sobre temas conocidos.",
        "lesen": "puedes comprender textos cotidianos y articulos breves sobre actualidad.",
        "schreiben": "puedes redactar textos conectados y argumentar brevemente.",
    },
    "B2": {
        "sprechen": "puedes defender una posicion, comparar opciones y negociar soluciones.",
        "hoeren": "puedes entender discusiones detalladas y audios semiautenticos.",
        "lesen": "puedes comprender textos complejos y distinguir argumentos principales/secundarios.",
        "schreiben": "puedes producir textos claros y bien estructurados con argumentacion.",
    },
    "C1": {
        "sprechen": "puedes expresarte de forma fluida, matizada y casi espontanea.",
        "hoeren": "puedes entender discursos extensos aun con estructura implícita.",
        "lesen": "puedes comprender textos exigentes y detectar matices de estilo/registro.",
        "schreiben": "puedes escribir textos elaborados con cohesion y precision alta.",
    },
    "C2": {
        "sprechen": "puedes argumentar con precision fina, reformular y responder con total naturalidad.",
        "hoeren": "puedes entender practicamente todo, incluso ritmo rapido y referencias implicitas.",
        "lesen": "puedes leer con soltura textos de alta complejidad y analizar su intencion.",
        "schreiben": "puedes producir textos sofisticados con tono y estructura totalmente controlados.",
    },
}

DEFAULT_EXAM_TOPICS: dict[ExamSection, list[str]] = {
    "sprechen": ["Alltag", "Arbeit und Studium", "Gesundheit", "Digitale Medien", "Wohnen"],
    "hoeren": ["Kundendienst", "Universitat", "Radiointerview", "Arbeitswelt", "Reiseorganisation"],
    "lesen": ["Zeitungsartikel", "E-Mail", "Informationsblatt", "Blogbeitrag", "Forumdiskussion"],
    "schreiben": ["Formelle E-Mail", "Beschwerde", "Meinungsforum", "Bewerbung", "Bericht"],
    "grammatik": ["Nebensatze", "Prateritum/Perfekt", "Kasus", "Relativsatze", "Konnektoren"],
    "wortschatz": ["Arbeit", "Gesellschaft", "Reisen", "Gesundheit", "Technologie"],
    "verben": ["Trennbare Verben", "Modalverben", "Passiv", "Konjunktiv II", "Verbvalenz"],
}

WRITING_WORD_TARGET: dict[str, str] = {
    "A1": "40-60",
    "A2": "60-90",
    "B1": "120-160",
    "B2": "180-230",
    "C1": "220-280",
    "C2": "260-320",
}

SPEAKING_TIME_TARGET: dict[str, str] = {
    "A1": "45-60 segundos",
    "A2": "60-90 segundos",
    "B1": "2-3 minutos",
    "B2": "3-4 minutos",
    "C1": "4-5 minutos",
    "C2": "5-6 minutos",
}


def level_group(level: str) -> Literal["basic", "independent", "advanced"]:
    if level in {"A1", "A2"}:
        return "basic"
    if level in {"B1", "B2"}:
        return "independent"
    return "advanced"


def section_for_cefr(section: ExamSection) -> Literal["sprechen", "hoeren", "lesen", "schreiben"]:
    if section in {"grammatik", "wortschatz", "verben"}:
        return "schreiben"
    return section


def pick_exam_topic(section: ExamSection, topic: str | None) -> str:
    if topic:
        clean = " ".join(topic.strip().split())
        if clean:
            return clean[:120]
    return random.choice(DEFAULT_EXAM_TOPICS.get(section, ["Alltag"]))


def testdaf_bridge_note(level: str, exam: ExamName) -> str:
    if exam == "testdaf" and CEFR_RANK.get(level, 0) < CEFR_RANK.get("B2", 3):
        return (
            "Nota: TestDaF oficial se orienta normalmente a B2-C1. "
            "Este ejercicio esta adaptado como puente progresivo."
        )
    return ""


def build_official_basis(exam: ExamName, section: ExamSection, level: str) -> str:
    cefr_key = section_for_cefr(section)
    cefr_line = CEFR_CAN_DO.get(level, CEFR_CAN_DO[DEFAULT_LEVEL]).get(
        cefr_key,
        CEFR_CAN_DO[DEFAULT_LEVEL]["sprechen"],
    )
    basis = EXAM_OFFICIAL_BASIS[exam]
    if section in {"grammatik", "wortschatz", "verben"}:
        basis = (
            f"{basis} Para {EXAM_SECTION_NAMES[section]} se aplica practica "
            "lexicogramatical alineada a criterios MCER y formatos de examen."
        )
    note = testdaf_bridge_note(level=level, exam=exam)
    if note:
        basis = f"{basis} {note}"
    return f"{basis} MCER {level}: {cefr_line}"


def build_speaking_pack(level: str, topic: str, exam: ExamName) -> str:
    group = level_group(level)
    follow_up = {
        "basic": "Stelle 3 kurze Zusatzfragen.",
        "independent": "Erganzend: nenne Vor- und Nachteile mit einem Beispiel.",
        "advanced": "Erganzend: vergleiche Gegenposition und ziehe ein begrundetes Fazit.",
    }[group]
    interaction_turns = {
        "basic": "4-6 turnos",
        "independent": "8-10 turnos",
        "advanced": "10-12 turnos",
    }[group]
    return "\n".join(
        [
            "1) Simulation de Sprechen (formato oficial adaptado)",
            f"Thema: {topic}",
            f"- Monologo guiado: {SPEAKING_TIME_TARGET[level]} sobre el tema.",
            f"- Interaccion: {interaction_turns} con repreguntas y reformulacion.",
            f"- Tarea extra: {follow_up}",
            "",
            "2) Guion de examen",
            "- Fase A: presentacion breve del tema y contexto.",
            "- Fase B: posicion personal con razones claras.",
            "- Fase C: reaccion a una opinion contraria y cierre.",
            "",
            "3) Criterios MCER a vigilar",
            "- Adecuacion a la consigna y claridad del mensaje.",
            "- Correccion gramatical, orden verbal y conectores.",
            "- Riqueza de vocabulario y naturalidad pragmatica.",
            "- Fluidez, pronunciacion y control del turno.",
            "",
            "4) Mini checklist antes de enviar respuesta",
            "- Respondi exactamente a la pregunta.",
            "- Use al menos 2 conectores (weil, deshalb, obwohl...).",
            "- Cerre con una idea final clara.",
        ]
    )


def build_listening_pack(level: str, topic: str, exam: ExamName) -> str:
    group = level_group(level)
    script = {
        "basic": (
            "Guten Tag, hier ist Anna. Ich rufe wegen eines Termins an. "
            "Am Dienstag um zehn Uhr kann ich leider nicht kommen. "
            "Haben Sie am Mittwoch einen freien Termin?"
        ),
        "independent": (
            "Im Radio sprechen zwei Personen uber Homeoffice. "
            "Eine Person findet die Flexibilitat gut, die andere kritisiert fehlenden Teamkontakt. "
            "Beide nennen konkrete Beispiele aus dem Arbeitsalltag."
        ),
        "advanced": (
            "In einem Fachpodcast wird diskutiert, wie KI Arbeitsprofile verandert. "
            "Die Expertin unterscheidet kurzfristige Effizienzgewinne und langfristige Qualifikationsrisiken "
            "und fordert gezielte Weiterbildung."
        ),
    }[group]
    return "\n".join(
        [
            "1) Simulation de Horen (formato oficial adaptado)",
            f"Kontext: {topic}",
            "Lee en voz alta el siguiente guion (o usa TTS) y escuchalo 2 veces:",
            f'"{script}"',
            "",
            "2) Preguntas de comprension",
            "- Idea principal del audio en 1 frase.",
            "- 3 datos especificos (quien, que, cuando/por que).",
            "- Intencion del hablante (informar, pedir, convencer, etc.).",
            "",
            "3) Tarea tipo examen",
            "- Marca V/F para 5 afirmaciones que tu mismo redactes del audio.",
            "- Corrige las falsas con una cita breve del guion.",
            "",
            "4) Criterios MCER",
            "- Comprension global + detalle relevante.",
            "- Deteccion de actitud/intencion del hablante.",
            "- Precision al reformular sin inventar informacion.",
        ]
    )


def build_reading_pack(level: str, topic: str, exam: ExamName) -> str:
    group = level_group(level)
    text = {
        "basic": (
            "Im Stadtzentrum gibt es seit kurzem einen neuen Wochenmarkt. "
            "Viele Bewohner kaufen dort frisches Obst und Gemuse. "
            "Der Markt ist jeden Samstag von 8 bis 14 Uhr geoffnet."
        ),
        "independent": (
            "Viele Firmen bieten inzwischen hybride Arbeitsmodelle an. "
            "Mitarbeitende schatzen die Flexibilitat, berichten aber auch von schwieriger Teamkoordination. "
            "Experten empfehlen feste Kommunikationsregeln, damit Projekte nicht langsamer werden."
        ),
        "advanced": (
            "Ein Leitartikel analysiert, warum digitale Bildung oft an Umsetzungsproblemen scheitert. "
            "Nicht die Technik selbst, sondern fehlende didaktische Konzepte seien das Kernproblem. "
            "Der Autor pladiert fur evidenzbasierte Pilotprojekte statt symbolischer Reformen."
        ),
    }[group]
    return "\n".join(
        [
            "1) Simulation de Lesen (formato oficial adaptado)",
            f"Textthema: {topic}",
            f"Texto base: {text}",
            "",
            "2) Preguntas tipo examen",
            "- Que afirma el texto exactamente y que solo sugiere.",
            "- 4 preguntas de opcion multiple (A/B/C) sobre detalle.",
            "- 1 pregunta de inferencia (intencion del autor).",
            "",
            "3) Tarea de precision",
            "- Subraya conectores y explica su funcion.",
            "- Resume el texto en 2 frases sin copiar literal.",
            "",
            "4) Criterios MCER",
            "- Comprension global y selectiva.",
            "- Localizacion de informacion concreta.",
            "- Diferenciacion entre hecho, opinion e inferencia.",
        ]
    )


def build_writing_pack(level: str, topic: str, exam: ExamName) -> str:
    group = level_group(level)
    prompt = {
        "basic": (
            "Schreibe eine kurze Nachricht an eine Freundin/einen Freund. "
            "Erklare, warum du heute keine Zeit hast und mache einen neuen Vorschlag."
        ),
        "independent": (
            "Schreibe einen Forumsbeitrag zum Thema Homeoffice: Vorteile, Nachteile, "
            "deine eigene Erfahrung und ein Vorschlag fur die Zukunft."
        ),
        "advanced": (
            "Verfasse einen strukturierten Stellungnahmetext: "
            "Welche Rolle soll KI in der schulischen Bewertung spielen? "
            "Begrunde deine Position und diskutiere Gegenargumente."
        ),
    }[group]
    return "\n".join(
        [
            "1) Simulation de Schreiben (formato oficial adaptado)",
            f"Thema: {topic}",
            f"Produccion objetivo: {WRITING_WORD_TARGET[level]} palabras.",
            f"Consigna: {prompt}",
            "",
            "2) Estructura sugerida",
            "- Introduccion: contexto + objetivo del texto.",
            "- Desarrollo: 2 ideas con ejemplo concreto.",
            "- Cierre: conclusion o accion solicitada.",
            "",
            "3) Revision obligatoria (autocorreccion)",
            "- Verbo en segunda posicion en Hauptsatz.",
            "- Comas antes de subordinadas frecuentes (weil, dass, wenn...).",
            "- Articulos/casos y concordancia.",
            "- Registro adecuado (formal o informal).",
            "",
            "4) Criterios MCER",
            "- Coherencia, cohesion y logro de tarea.",
            "- Correccion linguistica y riqueza expresiva.",
            "- Adecuacion al destinatario y al formato de examen.",
        ]
    )


def build_grammar_pack(level: str, topic: str, exam: ExamName) -> str:
    group = level_group(level)
    items = {
        "basic": [
            "Ich _____ (sein) heute zu Hause.",
            "Wir _____ (haben) morgen einen Termin.",
            "Er kommt nicht, _____ er krank ist. (weil/deshalb)",
            "Ich fahre _____ Berlin. (nach/zu)",
            "Das ist _____ Buch. (mein/meine)",
            "_____ du morgen Zeit? (Hast/Bist)",
        ],
        "independent": [
            "Wenn ich mehr Zeit _____, _____ ich einen Deutschkurs. (haben/machen)",
            "Ich glaube, dass er heute nicht _____ . (kommen)",
            "Obwohl es regnet, _____ wir spazieren. (gehen)",
            "Das ist der Mann, _____ ich gestern getroffen habe. (der/den)",
            "Sie interessiert sich _____ Politik. (fuer/an)",
            "Am Wochenende _____ ich viel gearbeitet. (habe/bin)",
        ],
        "advanced": [
            "Hatte ich fruher begonnen, _____ ich jetzt weniger Stress. (haben)",
            "Die Frage, _____ in der Studie gestellt wurde, bleibt relevant. (die/deren)",
            "Er argumentiert so, _____ kein Widerspruch moglich scheint. (dass/sodass)",
            "Nicht nur die Kosten, sondern auch der Nutzen _____ berucksichtigt werden. (muss/mussen)",
            "Je mehr Daten verfugbar sind, desto praziser _____ die Prognose. (werden/wird)",
            "Es ware sinnvoll, die Massnahme schrittweise _____. (einfuehren/eingefuehrt)",
        ],
    }[group]
    return "\n".join(
        [
            "1) Bloque de Grammatik (alineado MCER y formato de examen)",
            f"Fokus: {topic}",
            "Resuelve los siguientes items sin mirar apuntes:",
            *[f"{idx}. {item}" for idx, item in enumerate(items, start=1)],
            "",
            "2) Correccion guiada",
            "- Explica por que la opcion correcta encaja en cada frase.",
            "- Reescribe 3 frases cambiando tiempo verbal o conector.",
            "",
            "3) Transferencia a examen",
            "- Convierte 2 frases en preguntas.",
            "- Convierte 2 frases en Nebensatz con weil/dass/obwohl.",
        ]
    )


def build_vocabulary_pack(level: str, topic: str, exam: ExamName) -> str:
    group = level_group(level)
    tasks = {
        "basic": [
            "Completa: Ich _____ Deutsch jeden Tag. (lerne/lernst)",
            "Sinonimo simple de 'glucklich': _____",
            "Antonym de 'teuer': _____",
            "Escribe 5 palabras del campo semantico de trabajo/estudio.",
        ],
        "independent": [
            "Completa colocaciones: eine Entscheidung _____; ein Problem _____.",
            "Reformula con sinonimos: wichtig, schwierig, verbessern, Erfahrung.",
            "Escribe 6 conectores utiles para argumentar y su funcion.",
            "Crea 4 frases con vocabulario de {topic}.",
        ],
        "advanced": [
            "Sustituye por registro academico: gut/schlecht/denken/machen.",
            "Explica diferencia de matiz entre: behaupten, meinen, argumentieren.",
            "Escribe 5 nominalizaciones utiles para texto formal.",
            "Redacta 4 frases con collocations avanzadas sobre {topic}.",
        ],
    }[group]
    return "\n".join(
        [
            "1) Bloque de Wortschatz (alineado a criterios oficiales)",
            f"Themenfeld: {topic}",
            *[f"{idx}. {task}" for idx, task in enumerate(tasks, start=1)],
            "",
            "2) Produccion activa",
            "- Elige 8 palabras nuevas y crea una mini historia de 6-8 frases.",
            "- Marca las palabras que volveras a repasar en 24h y 72h.",
            "",
            "3) Criterios MCER",
            "- Adecuacion lexical al contexto.",
            "- Variedad y precision semantica.",
            "- Control de registro (informal/formal).",
        ]
    )


def build_verbs_pack(level: str, topic: str, exam: ExamName) -> str:
    group = level_group(level)
    tasks = {
        "basic": [
            "Conjuga en presente: ich gehen, du sprechen, er arbeiten.",
            "Pasa a Perfekt: Ich lerne Deutsch. / Wir kaufen Brot.",
            "Completa con modal correcto: Ich _____ heute nicht kommen.",
            "Ordena: heute / ich / ins Buro / gehe.",
        ],
        "independent": [
            "Transforma a Prateritum: Er sagt die Wahrheit. / Wir fahren nach Berlin.",
            "Usa Konjunktiv II para peticion cortesa (3 frases).",
            "Convierte 3 frases activas a pasiva.",
            "Corrige posicion verbal en 4 frases con Nebensatz.",
        ],
        "advanced": [
            "Reescribe con participiales donde sea natural (2 frases).",
            "Parafrasea con estructuras de infinitivo con zu (3 frases).",
            "Usa Konjunktiv I/II para cita indirecta y distancia critica.",
            "Escribe 4 frases con verbos de regimen fijo + caso correcto.",
        ],
    }[group]
    return "\n".join(
        [
            "1) Bloque de Verben (control estructural para examen)",
            f"Contexto: {topic}",
            *[f"{idx}. {task}" for idx, task in enumerate(tasks, start=1)],
            "",
            "2) Micro-produccion",
            "- Crea un mini monologo de 8 frases usando al menos 5 verbos del bloque.",
            "- Verifica tiempo verbal, posicion del verbo y concordancia.",
            "",
            "3) Criterios MCER",
            "- Correccion morfologica y sintactica.",
            "- Flexibilidad para cambiar tiempo/modo con naturalidad.",
            "- Precision en estructuras complejas.",
        ]
    )


def build_exam_practice_content(level: str, exam: ExamName, section: ExamSection, topic: str) -> str:
    if section == "sprechen":
        return build_speaking_pack(level=level, topic=topic, exam=exam)
    if section == "hoeren":
        return build_listening_pack(level=level, topic=topic, exam=exam)
    if section == "lesen":
        return build_reading_pack(level=level, topic=topic, exam=exam)
    if section == "schreiben":
        return build_writing_pack(level=level, topic=topic, exam=exam)
    if section == "grammatik":
        return build_grammar_pack(level=level, topic=topic, exam=exam)
    if section == "wortschatz":
        return build_vocabulary_pack(level=level, topic=topic, exam=exam)
    return build_verbs_pack(level=level, topic=topic, exam=exam)


GRAMMAR_BANK: dict[str, list[tuple[str, str, list[str], str]]] = {
    "basic": [
        ("Ich ___ heute keine Zeit.", "habe", ["habe", "bin", "hatte"], "Verbform in Praesens: ich habe."),
        ("Wir gehen ins Kino, ___ es regnet.", "obwohl", ["weil", "obwohl", "damit"], "Gegensatz mit obwohl."),
        ("Morgen ___ ich frueh aufstehen.", "muss", ["muss", "musst", "muessen"], "Modalverb fuer ich: muss."),
        ("Das ist ___ Tasche.", "meine", ["mein", "meine", "meinen"], "Femininum Nominativ: meine Tasche."),
        ("___ du mir helfen?", "Kannst", ["Kann", "Kannst", "Kannet"], "Frage mit du: Kannst du...?"),
        ("Er kommt spaeter, ___ er noch arbeitet.", "weil", ["deshalb", "weil", "aber"], "Grundsatz mit weil."),
    ],
    "independent": [
        (
            "Ich finde, dass die Idee sehr gut ___.",
            "ist",
            ["ist", "war", "sei"],
            "Im Nebensatz steht das konjugierte Verb am Ende.",
        ),
        (
            "Wenn ich mehr Zeit haette, ___ ich oefter Deutsch sprechen.",
            "wuerde",
            ["werde", "wuerde", "wurde"],
            "Irreale Bedingung: wuerde + Infinitiv.",
        ),
        ("Sie interessiert sich ___ Politik.", "fuer", ["fuer", "an", "mit"], "sich interessieren fuer + Akkusativ."),
        (
            "Obwohl er krank war, ___ er zur Arbeit gegangen.",
            "ist",
            ["hat", "ist", "war"],
            "Perfekt von gehen mit sein.",
        ),
        (
            "Das ist der Mann, ___ ich gestern gesehen habe.",
            "den",
            ["der", "den", "dem"],
            "Relativpronomen Akkusativ maskulin: den.",
        ),
        (
            "Viele Probleme ___ durch bessere Planung geloest werden.",
            "koennen",
            ["kann", "koennen", "konnten"],
            "Plural Subjekt + Modalverb im Plural.",
        ),
    ],
    "advanced": [
        (
            "Je praeziser die Daten sind, desto verlaesslicher ___ die Prognose.",
            "wird",
            ["wird", "werden", "waere"],
            "Singular: die Prognose wird verlaesslicher.",
        ),
        (
            "Es ist wichtig, dass die Ergebnisse transparent ___ .",
            "kommuniziert werden",
            ["kommuniziert werden", "kommuniziert wird", "kommunizieren"],
            "Passiv mit Pluralobjekt: Ergebnisse ... werden.",
        ),
        (
            "Hatte man frueher reagiert, ___ die Folgen geringer gewesen.",
            "waeren",
            ["waeren", "wuerden", "seien"],
            "Irreale Vergangenheit im Konjunktiv II: waeren.",
        ),
        (
            "Die Frage, ___ im Bericht nur am Rand erscheint, ist zentral.",
            "die",
            ["die", "deren", "denen"],
            "Relativpronomen fuer Frage (feminin singular): die.",
        ),
        (
            "Nicht nur die Kosten, sondern auch der Nutzen ___ beruecksichtigt werden.",
            "muss",
            ["muss", "muessen", "musste"],
            "Bei nicht nur ... sondern auch richtet sich das Verb nach dem naeheren Subjekt.",
        ),
        (
            "Die Studie wurde kritisiert, weil ihre Methode kaum ___ sei.",
            "nachvollziehbar",
            ["nachvollziehbar", "nachvollziehen", "nachvollziehbarkeit"],
            "Praedikativadjektiv nach sei.",
        ),
    ],
}

VOCAB_BANK: dict[str, list[tuple[str, str, list[str], str]]] = {
    "basic": [
        ("Er macht jeden Tag ___.", "Sport", ["Sport", "sportlich", "gesportet"], "Feste Verbindung: Sport machen."),
        ("Ich moechte einen Termin ___.", "vereinbaren", ["vereinbaren", "aufmachen", "bekommen"], "Termin vereinbaren."),
        ("Das Gegenteil von teuer ist ___.", "guenstig", ["guenstig", "langsam", "hell"], "Antonym von teuer."),
        ("Wir haben ein grosses ___ geloest.", "Problem", ["Problem", "proben", "Programm"], "Kollokation: Problem loesen."),
        ("Sie hat viel ___ im Beruf.", "Erfahrung", ["Erfahrung", "Erfindung", "Erinnerung"], "Erfahrung im Beruf."),
        ("Bitte gib mir einen guten ___.", "Tipp", ["Tipp", "Ton", "Teil"], "Tipp geben."),
    ],
    "independent": [
        (
            "Die Firma hat eine wichtige Entscheidung ___.",
            "getroffen",
            ["getroffen", "gemacht", "genommen"],
            "Kollokation: eine Entscheidung treffen.",
        ),
        (
            "Wir muessen die Ergebnisse sorgfaeltig ___.",
            "auswerten",
            ["auswerten", "ausgehen", "austragen"],
            "Daten/Ergebnisse auswerten.",
        ),
        ("Das Projekt wurde deutlich ___.", "verbessert", ["verbessert", "verpasst", "vermischt"], "Verb im Kontext Projekt."),
        (
            "Sein Argument ist plausibel und gut ___.",
            "begruendet",
            ["begruendet", "gebaut", "bedient"],
            "Argumente begruenden.",
        ),
        (
            "Die Maßnahme hat sowohl Vor- als auch ___.",
            "Nachteile",
            ["Nachteile", "Nachbarn", "Nachrichten"],
            "Fester Ausdruck: Vor- und Nachteile.",
        ),
        ("Im Team braucht man klare ___.", "Absprachen", ["Absprachen", "Abgaben", "Abteile"], "Klarheit durch Absprachen."),
    ],
    "advanced": [
        (
            "Die Entscheidung hat weitreichende ___.",
            "Auswirkungen",
            ["Auswirkungen", "Ausfahrten", "Ausnahmen"],
            "Haeufige Verbindung in formellem Kontext.",
        ),
        (
            "Das Konzept ist theoretisch schluessig, aber praktisch kaum ___.",
            "umsetzbar",
            ["umsetzbar", "umsichtig", "umgezogen"],
            "Praedikativ: kaum umsetzbar.",
        ),
        (
            "Der Artikel beleuchtet die Frage aus einer neuen ___.",
            "Perspektive",
            ["Perspektive", "Person", "Prasenz"],
            "Aus einer Perspektive betrachten.",
        ),
        (
            "Die Autorin differenziert zwischen Ursache und ___.",
            "Folge",
            ["Folge", "Frage", "Falle"],
            "Semantisches Paar: Ursache und Folge.",
        ),
        (
            "Seine Position wirkt in sich ___.",
            "widerspruechlich",
            ["widerspruechlich", "widerstandslos", "wiederholt"],
            "Typische Bewertung von Argumenten.",
        ),
        (
            "Die Studie liefert nur begrenzte empirische ___.",
            "Evidenz",
            ["Evidenz", "Evolution", "Energie"],
            "Akademischer Ausdruck.",
        ),
    ],
}

VERB_BANK: dict[str, list[tuple[str, str, list[str], str]]] = {
    "basic": [
        ("Ich ___ morgen frueh auf.", "stehe", ["stehe", "steht", "stehst"], "Trennbares Verb: ich stehe ... auf."),
        ("Wir ___ heute Deutsch.", "lernen", ["lernen", "lernt", "lerne"], "Plural wir: lernen."),
        ("Sie ___ gestern zu Hause geblieben.", "ist", ["ist", "hat", "war"], "Perfekt mit sein: ist geblieben."),
        ("Kannst du mir bitte ___?", "helfen", ["helfen", "hilfst", "helfenst"], "Modal + Infinitiv am Ende."),
        ("Am Wochenende ___ ich meine Freunde.", "besuche", ["besuche", "besucht", "besuchen"], "ich + besuche."),
        ("Er ___ jeden Abend Musik.", "hoert", ["hoert", "hoere", "hoeren"], "3. Person singular."),
    ],
    "independent": [
        (
            "Wenn ich Zeit haette, ___ ich mehr lesen.",
            "wuerde",
            ["wuerde", "werde", "war"],
            "Konjunktiv II fuer hypothetische Aussagen.",
        ),
        ("Der Termin ___ auf naechste Woche verschoben.", "wurde", ["wurde", "ist", "hat"], "Passiv Praeteritum."),
        (
            "Ich habe versucht, frueher ___ .",
            "zu kommen",
            ["zu kommen", "kommen zu", "zugekommen"],
            "Infinitivkonstruktion mit zu.",
        ),
        (
            "Nachdem wir gegessen hatten, ___ wir spazieren.",
            "gingen",
            ["gingen", "gehen", "gegangen"],
            "Erzaehlung in der Vergangenheit.",
        ),
        (
            "Die Firma plant, neue Prozesse ___ .",
            "einzufuehren",
            ["einzufuehren", "einfuehrt", "eingefuehrt"],
            "planen + zu + Infinitiv.",
        ),
        (
            "Es haengt davon ab, ob er rechtzeitig ___ .",
            "ankommt",
            ["ankommt", "kommt an", "angekommen"],
            "Nebensatz mit ob: Verb am Ende.",
        ),
    ],
    "advanced": [
        (
            "Es waere sinnvoll, die Ergebnisse transparent ___ .",
            "darzustellen",
            ["darzustellen", "darstellt", "dargestellt"],
            "Adjektiv + zu-Infinitiv.",
        ),
        (
            "Die Daten lassen sich nur bedingt ___ .",
            "interpretieren",
            ["interpretieren", "interpretiert", "zu interpretieren"],
            "Reflexive Konstruktion: lassen sich + Infinitiv.",
        ),
        (
            "Er behauptete, man ___ die Risiken unterschätzt.",
            "habe",
            ["habe", "hat", "hatte"],
            "Indirekte Rede mit Konjunktiv I.",
        ),
        (
            "Die Maßnahme gilt als zu spaet ___ .",
            "eingefuehrt",
            ["eingefuehrt", "einzufuehren", "einfuehren"],
            "Partizip in praedikativem Gebrauch.",
        ),
        (
            "Es ist nicht auszuschliessen, dass sich der Trend weiter ___ .",
            "verstaerkt",
            ["verstaerkt", "verstaerken", "verstaerkte"],
            "dass-Satz: konjugiertes Verb am Ende.",
        ),
        (
            "Die Ergebnisse sollen kritisch ___ werden.",
            "eingeordnet",
            ["eingeordnet", "einordnen", "einzuordnen"],
            "Passiv + Partizip II.",
        ),
    ],
}

READING_LISTENING_CONTEXT: dict[str, dict[str, str]] = {
    "basic": {
        "reading": (
            "In unserer Stadt gibt es seit diesem Monat einen neuen Wochenmarkt. "
            "Viele Leute kaufen dort frisches Obst und Gemuese. "
            "Der Markt ist jeden Samstag von 8 bis 14 Uhr geoeffnet."
        ),
        "listening": (
            "Guten Tag, hier spricht Lara vom Sprachzentrum. "
            "Der Kurs beginnt am Montag um neun Uhr in Raum drei. "
            "Bitte bringen Sie ein Heft und einen Stift mit."
        ),
    },
    "independent": {
        "reading": (
            "Immer mehr Unternehmen testen hybride Arbeitsmodelle. "
            "Mitarbeitende schaetzen die Flexibilitaet, berichten aber von schwieriger Abstimmung im Team. "
            "Expertinnen empfehlen feste Kommunikationszeiten, um Missverstaendnisse zu vermeiden."
        ),
        "listening": (
            "In einem Interview erklaert ein Projektleiter, warum sein Team auf kurze taegliche Meetings umgestiegen ist. "
            "Seitdem laufen Absprachen schneller, jedoch empfinden manche Kolleginnen den Takt als zu hoch."
        ),
    },
    "advanced": {
        "reading": (
            "Ein Leitartikel argumentiert, dass digitale Transformation nur dann nachhaltig wirkt, "
            "wenn institutionelle Prozesse parallel reformiert werden. "
            "Technische Investitionen ohne Organisationsentwicklung erzeugen laut Autorin kaum langfristigen Mehrwert."
        ),
        "listening": (
            "Ein Podcast diskutiert die Folgen datengetriebener Entscheidungen in der Bildungspolitik. "
            "Die Expertin betont, dass Effizienzgewinne gegen Fairness- und Transparenzfragen abgewogen werden muessen."
        ),
    },
}

FLASHCARD_TOPIC_BANK: dict[str, list[tuple[str, str, str, list[str]]]] = {
    "arbeit": [
        ("der Lebenslauf", "curriculum", "Ich aktualisiere meinen Lebenslauf.", ["cv", "curriculum vitae"]),
        ("die Bewerbung", "solicitud", "Ich schreibe eine Bewerbung.", ["candidatura"]),
        ("die Frist", "plazo", "Die Frist endet am Freitag.", ["fecha limite"]),
        ("die Gehaltserhoehung", "subida salarial", "Sie verhandelt ueber eine Gehaltserhoehung.", ["aumento de sueldo"]),
        ("kuendigen", "renunciar", "Er will den Job nicht kuendigen.", ["dejar el trabajo"]),
        ("die Besprechung", "reunion", "Wir haben um zehn Uhr eine Besprechung.", ["meeting"]),
    ],
    "pruefung": [
        ("die Vorbereitung", "preparacion", "Die Vorbereitung dauert zwei Wochen.", ["preparar"]),
        ("bestehen", "aprobar", "Ich moechte die Pruefung bestehen.", ["aprobar un examen"]),
        ("durchfallen", "suspender", "Er ist letztes Jahr durchgefallen.", ["reprobar"]),
        ("die Aufgabe", "tarea", "Die dritte Aufgabe war schwer.", ["ejercicio"]),
        ("bewerten", "evaluar", "Die Lehrerin bewertet den Text.", ["calificar"]),
        ("das Ergebnis", "resultado", "Mein Ergebnis war besser als erwartet.", ["nota"]),
    ],
    "alltag": [
        ("einkaufen", "hacer la compra", "Ich gehe heute einkaufen.", ["comprar"]),
        ("sich entspannen", "relajarse", "Am Abend moechte ich mich entspannen.", ["descansar"]),
        ("die Gewohnheit", "costumbre", "Lesen ist eine gute Gewohnheit.", ["habito"]),
        ("fruehstuecken", "desayunar", "Wir fruehstuecken um sieben.", ["tomar desayuno"]),
        ("die Strecke", "trayecto", "Die Strecke zur Uni ist kurz.", ["recorrido"]),
        ("das Viertel", "barrio", "Ich wohne in einem ruhigen Viertel.", ["zona"]),
    ],
    "gesundheit": [
        ("sich erholen", "recuperarse", "Nach der Grippe muss ich mich erholen.", ["recuperar"]),
        ("die Beschwerde", "molestia", "Die Beschwerde dauert schon drei Tage.", ["sintoma"]),
        ("verschreiben", "recetar", "Der Arzt verschreibt ein Medikament.", ["receta"]),
        ("die Behandlung", "tratamiento", "Die Behandlung beginnt morgen.", ["terapia"]),
        ("die Vorsorge", "prevencion", "Vorsorge ist besser als spaete Therapie.", ["prevencion medica"]),
        ("anstrengend", "agotador", "Der Tag war sehr anstrengend.", ["cansado", "duro"]),
    ],
    "technik": [
        ("die Anwendung", "aplicacion", "Diese Anwendung spart Zeit.", ["app"]),
        ("zuverlaessig", "fiable", "Das System ist sehr zuverlaessig.", ["confiable"]),
        ("die Schnittstelle", "interfaz", "Wir brauchen eine neue Schnittstelle.", ["interface"]),
        ("speichern", "guardar", "Bitte speichern Sie die Datei.", ["guardar archivo"]),
        ("aktualisieren", "actualizar", "Ich muss das Programm aktualisieren.", ["update"]),
        ("die Datenschutzrichtlinie", "politica de privacidad", "Jede Plattform braucht eine Datenschutzrichtlinie.", ["privacidad"]),
    ],
}


def make_generated_question(
    *,
    qid: str,
    qtype: Literal["mcq", "cloze", "short", "open"],
    prompt: str,
    answer: str = "",
    options: list[str] | None = None,
    explanation: str = "",
    max_points: int = 1,
    support_text: str | None = None,
    keywords: list[str] | None = None,
    min_words: int = 20,
) -> GeneratedQuestionDict:
    return {
        "id": qid,
        "type": qtype,
        "prompt": prompt,
        "support_text": support_text,
        "options": options or [],
        "answer": answer,
        "explanation": explanation,
        "max_points": max_points,
        "keywords": keywords or [],
        "min_words": min_words,
    }


def to_public_question(question: GeneratedQuestionDict) -> PracticeQuestion:
    return PracticeQuestion(
        id=question["id"],
        type=question["type"],
        prompt=question["prompt"],
        support_text=question.get("support_text"),
        options=list(question.get("options", [])),
        max_points=int(question.get("max_points", 1)),
    )


def sample_from_bank(bank: list[Any], count: int) -> list[Any]:
    if count >= len(bank):
        return list(bank)
    return random.sample(bank, k=count)


def generated_objective_questions(
    *,
    module: ExamSection,
    level: str,
    topic: str,
    count: int,
) -> tuple[list[GeneratedQuestionDict], str]:
    group = level_group(level)
    questions: list[GeneratedQuestionDict] = []
    if module == "grammatik":
        rows = sample_from_bank(GRAMMAR_BANK[group], min(count, len(GRAMMAR_BANK[group])))
        for idx, (prompt, answer, options, explanation) in enumerate(rows, start=1):
            qid = f"g{idx}"
            questions.append(
                make_generated_question(
                    qid=qid,
                    qtype="mcq",
                    prompt=prompt,
                    answer=answer,
                    options=options,
                    explanation=explanation,
                    max_points=2,
                )
            )
        instructions = "Completa cada item y elige la opcion correcta."
        return questions, instructions

    if module == "wortschatz":
        rows = sample_from_bank(VOCAB_BANK[group], min(count, len(VOCAB_BANK[group])))
        for idx, (prompt, answer, options, explanation) in enumerate(rows, start=1):
            qid = f"w{idx}"
            questions.append(
                make_generated_question(
                    qid=qid,
                    qtype="mcq",
                    prompt=prompt,
                    answer=answer,
                    options=options,
                    explanation=explanation,
                    max_points=2,
                )
            )
        instructions = "Selecciona la opcion lexical mas natural en contexto."
        return questions, instructions

    if module == "verben":
        rows = sample_from_bank(VERB_BANK[group], min(count, len(VERB_BANK[group])))
        for idx, (prompt, answer, options, explanation) in enumerate(rows, start=1):
            qid = f"v{idx}"
            questions.append(
                make_generated_question(
                    qid=qid,
                    qtype="mcq",
                    prompt=prompt,
                    answer=answer,
                    options=options,
                    explanation=explanation,
                    max_points=2,
                )
            )
        instructions = "Trabaja conjugacion, posicion verbal y estructuras clave."
        return questions, instructions

    if module in {"lesen", "hoeren"}:
        context = READING_LISTENING_CONTEXT[group]["reading" if module == "lesen" else "listening"]
        rows = [
            (
                "Was ist das Hauptthema des Textes/Audios?",
                "organisation",
                ["organisation", "wetter", "sport"],
                "El texto trata sobre organizacion de trabajo/procesos.",
            ),
            (
                "Welche Herausforderung wird genannt?",
                "abstimmung",
                ["abstimmung", "finanzen", "transport"],
                "Se menciona coordinacion/comunicacion.",
            ),
            (
                "Welche Loesung wird vorgeschlagen?",
                "klare regeln",
                ["klare regeln", "mehr urlaub", "neue gebaeude"],
                "Se proponen reglas claras o proceso definido.",
            ),
        ]
        selected = rows[: min(count, len(rows))]
        for idx, (prompt, answer, options, explanation) in enumerate(selected, start=1):
            qid = f"{module[0]}{idx}"
            questions.append(
                make_generated_question(
                    qid=qid,
                    qtype="mcq",
                    prompt=prompt,
                    answer=answer,
                    options=options,
                    explanation=explanation,
                    max_points=2,
                    support_text=context,
                )
            )
        instructions = (
            "Lee/escucha el texto base y responde a las preguntas de comprension."
            if module == "lesen"
            else "Escucha el guion en voz alta dos veces y responde por comprension."
        )
        return questions, instructions

    return questions, "Responde las preguntas."


def generated_open_questions(
    *,
    module: ExamSection,
    level: str,
    topic: str,
    count: int,
) -> tuple[list[GeneratedQuestionDict], str]:
    base_topic = topic or "Alltag"
    if module == "sprechen":
        prompts = [
            (
                f"Sprich ueber das Thema '{base_topic}' und erklaere deine persoenliche Position.",
                ["ich denke", "weil", "zum beispiel"],
            ),
            (
                "Reagiere auf eine Gegenmeinung und verteidige deine Sicht in klaren Schritten.",
                ["einerseits", "andererseits", "deshalb"],
            ),
            (
                "Beende mit einer konkreten Empfehlung fuer den Alltag.",
                ["ich empfehle", "sollte", "am wichtigsten"],
            ),
        ]
        instructions = (
            "Contesta en aleman como en examen oral: claridad, conectores y estructura. "
            "Puedes escribir tu respuesta en texto si no usas micro."
        )
    else:
        prompts = [
            (
                f"Schreibe einen strukturierten Text zum Thema '{base_topic}' mit Einleitung, Hauptteil und Schluss.",
                ["einleitung", "weil", "fazit"],
            ),
            (
                "Formuliere Vorteile und Nachteile mit mindestens einem konkreten Beispiel.",
                ["vorteile", "nachteile", "zum beispiel"],
            ),
            (
                "Schliesse mit einer klaren Empfehlung oder Entscheidung.",
                ["abschliessend", "ich empfehle", "zusammenfassend"],
            ),
        ]
        instructions = (
            "Escribe en aleman respetando formato de examen escrito: estructura, coherencia y correccion."
        )

    selected = prompts[: min(count, len(prompts))]
    questions: list[GeneratedQuestionDict] = []
    min_words = {"A1": 30, "A2": 45, "B1": 70, "B2": 110, "C1": 150, "C2": 170}.get(level, 70)
    for idx, (prompt, keywords) in enumerate(selected, start=1):
        qid = f"o{idx}"
        questions.append(
            make_generated_question(
                qid=qid,
                qtype="open",
                prompt=prompt,
                answer="",
                explanation="Respuesta abierta evaluada por contenido, claridad y correccion.",
                max_points=5,
                keywords=keywords,
                min_words=min_words,
            )
        )
    return questions, instructions


def build_question_set(
    *,
    level: str,
    module: ExamSection,
    topic: str,
    count: int,
) -> tuple[list[GeneratedQuestionDict], str]:
    if module in {"sprechen", "schreiben"}:
        return generated_open_questions(module=module, level=level, topic=topic, count=count)
    return generated_objective_questions(module=module, level=level, topic=topic, count=count)


def normalize_answer_text(text: str) -> str:
    return normalize_for_matching(" ".join(text.strip().split()))


def parse_first_json_object(raw_text: str) -> dict[str, Any]:
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
    raise RuntimeError("No se pudo parsear JSON de evaluacion.")


def evaluate_open_answer_with_llm(
    *,
    question: GeneratedQuestionDict,
    user_answer: str,
    level: str,
    module: ExamSection,
) -> tuple[int, bool, str, str]:
    provider = resolve_provider()
    if provider == "rulebased":
        raise RuntimeError("LLM no disponible para correccion avanzada.")

    max_points = max(1, int(question.get("max_points", 5)))
    module_label = EXAM_SECTION_NAMES.get(module, module)
    keywords = question.get("keywords") or []
    keywords_text = ", ".join(keywords) if keywords else "-"
    prompt = GOETHE_OPEN_EVAL_PROMPT.format(
        level=level,
        module_label=module_label,
        max_points=max_points,
        question_prompt=question.get("prompt", ""),
        keywords_text=keywords_text,
        user_answer=user_answer,
    )

    raw_text = ""
    if provider == "ollama":
        eval_model = pick_ollama_chat_model() if OLLAMA_SPEED_PRESET == "turbo" else OLLAMA_MODEL
        payload = {
            "model": eval_model,
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": {
                **ollama_chat_options(for_feedback=True),
                "num_predict": min(550, max(220, OLLAMA_FEEDBACK_MAX_TOKENS)),
                "temperature": 0.15,
            },
            "messages": [
                {"role": "system", "content": "Devuelve SOLO JSON valido."},
                {"role": "user", "content": prompt},
            ],
        }
        response = http_post_json(
            f"{OLLAMA_BASE_URL}/api/chat",
            payload,
            timeout=max(18, min(OLLAMA_CHAT_TIMEOUT, 35)),
        )
        message = response.get("message", {})
        raw_text = str(message.get("content", "")).strip()

    if not raw_text:
        raise RuntimeError("Evaluacion LLM vacia.")

    parsed = parse_first_json_object(raw_text)
    score = int(parsed.get("score", 0))
    score = max(0, min(score, max_points))
    corrected = str(parsed.get("corrected_answer_de", "")).strip()
    strength = str(parsed.get("strength", "")).strip()
    next_step = str(parsed.get("next_step", "")).strip()
    critical_errors_raw = parsed.get("critical_errors", [])
    if not isinstance(critical_errors_raw, list):
        critical_errors_raw = [critical_errors_raw]
    critical_errors = [
        str(item).strip()
        for item in critical_errors_raw
        if isinstance(item, (str, int, float)) and str(item).strip()
    ][:4]

    feedback_parts: list[str] = []
    if strength:
        feedback_parts.append(f"Fortaleza: {strength}")
    if critical_errors:
        numbered = " | ".join(f"{idx + 1}) {item}" for idx, item in enumerate(critical_errors))
        feedback_parts.append(f"Errores que cuestan puntos: {numbered}")
    if next_step:
        feedback_parts.append(f"Siguiente mini-paso: {next_step}")
    feedback = " ".join(feedback_parts).strip()
    if not feedback:
        feedback = "Correccion completada con rubrica Goethe."
    if not corrected:
        corrected = autopunctuate_monologue_text(user_answer)

    pass_threshold = max(1, int(max_points * 0.6))
    return score, score >= pass_threshold, feedback, corrected


def evaluate_objective_answer(question: GeneratedQuestionDict, user_answer: str) -> tuple[int, bool, str]:
    expected = normalize_answer_text(question.get("answer", ""))
    received = normalize_answer_text(user_answer)
    if not expected:
        return 0, False, "No hay solucion configurada para este item."
    if received == expected:
        return int(question.get("max_points", 1)), True, "Correcto."

    # Accept close lexical variants with high similarity for short-answer items.
    if question["type"] in {"cloze", "short"}:
        ratio = SequenceMatcher(None, received, expected).ratio()
        if ratio >= 0.86:
            partial = max(1, int(question.get("max_points", 1)) - 1)
            return partial, False, "Casi correcto; revisa ortografia/forma exacta."

    feedback = (
        f"Incorrecto. Respuesta esperada: {question.get('answer', '-')}. "
        f"{question.get('explanation', '')}".strip()
    )
    return 0, False, feedback


def evaluate_open_answer(
    question: GeneratedQuestionDict,
    user_answer: str,
    *,
    level: str,
    module: ExamSection,
) -> tuple[int, bool, str, str]:
    cleaned = " ".join(user_answer.strip().split())
    if not cleaned:
        return 0, False, "Sin respuesta. Escribe o dicta una respuesta en aleman.", ""

    max_points = int(question.get("max_points", 5))
    try:
        return evaluate_open_answer_with_llm(
            question=question,
            user_answer=cleaned,
            level=level,
            module=module,
        )
    except Exception:
        # Fallback robusto para que siempre haya correccion aunque el LLM falle.
        pass

    normalized = normalize_answer_text(cleaned)
    words = GERMAN_TOKEN_RE.findall(cleaned)
    min_words = max(20, int(question.get("min_words", 40)))
    keywords = [normalize_for_matching(k) for k in question.get("keywords", []) if k]
    keyword_hits = sum(1 for keyword in keywords if keyword in normalized)
    connectors = ["weil", "deshalb", "obwohl", "dass", "damit", "einerseits", "andererseits"]
    connector_hits = sum(1 for connector in connectors if re.search(rf"\b{re.escape(connector)}\b", normalized))

    score = 0
    if len(words) >= int(min_words * 0.8):
        score += 2
    elif len(words) >= int(min_words * 0.5):
        score += 1

    if keywords:
        score += min(2, max(0, keyword_hits))
    else:
        score += 1

    if connector_hits >= 1:
        score += 1
    if re.search(r"[.!?]", cleaned):
        score += 1

    score = max(0, min(score, max_points))
    corrected = autopunctuate_monologue_text(cleaned)
    issues = detect_monologue_issues(raw_text=cleaned, normalized_text=corrected)
    feedback_parts = [
        f"Longitud: {len(words)} palabras (objetivo aprox. {min_words}).",
        f"Palabras clave cubiertas: {keyword_hits}/{len(keywords)}." if keywords else "Sin palabras clave obligatorias.",
    ]
    if issues:
        first_issue = issues[0]
        feedback_parts.append(f"Mejora prioritaria: {first_issue[2]}")
    if corrected and corrected != cleaned:
        feedback_parts.append(f"Version mejorada sugerida: {corrected}")
    pass_threshold = max(1, int(max_points * 0.6))
    return score, score >= pass_threshold, " ".join(feedback_parts), corrected


def summarize_score(score: int, max_score: int) -> str:
    if max_score <= 0:
        return "No se pudo evaluar."
    percent = (score / max_score) * 100
    if percent >= 85:
        return "Muy buen resultado. Ya tienes base solida para examen."
    if percent >= 70:
        return "Buen resultado. Falta afinar precision para subir nota."
    if percent >= 55:
        return "Resultado intermedio. Conviene reforzar gramatica y estructura."
    return "Resultado bajo. Repite bloque corto y corrige item por item."


def build_mock_meta_title(exam: ExamName, module: ExamSection, level: str) -> str:
    return f"Simulacro {EXAM_DISPLAY_NAMES[exam]} · {EXAM_SECTION_NAMES[module]} · {level}"


def pick_flashcard_topic(topic: str) -> str:
    normalized = normalize_for_matching(topic)
    for key in FLASHCARD_TOPIC_BANK:
        if key in normalized:
            return key
    return "alltag"


def build_flashcards(level: str, topic: str, count: int) -> list[dict[str, Any]]:
    topic_key = pick_flashcard_topic(topic)
    primary = list(FLASHCARD_TOPIC_BANK.get(topic_key, []))
    fallback = list(FLASHCARD_TOPIC_BANK["alltag"])
    pool = primary + [item for item in fallback if item not in primary]

    group = level_group(level)
    if group == "basic":
        selected_pool = pool[: max(count + 3, 10)]
    elif group == "independent":
        selected_pool = pool
    else:
        selected_pool = pool + list(FLASHCARD_TOPIC_BANK.get("technik", []))

    chosen = sample_from_bank(selected_pool, min(count, len(selected_pool)))
    cards: list[dict[str, Any]] = []
    for idx, (front, back, example, synonyms) in enumerate(chosen, start=1):
        cards.append(
            {
                "id": f"c{idx}",
                "front": front,
                "back": back,
                "example": example,
                "synonyms": synonyms,
            }
        )
    return cards


def evaluate_flashcard_answer(expected: str, synonyms: list[str], user_answer: str) -> tuple[bool, str]:
    guess = normalize_answer_text(user_answer)
    candidates = [normalize_answer_text(expected)] + [normalize_answer_text(item) for item in synonyms]
    if guess in candidates:
        return True, "Correcto."
    similarity = max((SequenceMatcher(None, guess, candidate).ratio() for candidate in candidates), default=0.0)
    if similarity >= 0.8:
        return True, "Muy cerca; se considera correcto."
    return False, "No exacto; revisa matiz de significado."


def http_post_json(url: str, payload: dict, timeout: int = OLLAMA_REQUEST_TIMEOUT) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = UrlRequest(
        url=url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError(
            f"Ollama timeout after {timeout}s. The model may still be loading. Try again."
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"Ollama not reachable: {exc.reason}") from exc
    except OSError as exc:
        raise RuntimeError(f"Ollama OS/network error: {exc}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ollama returned invalid JSON.") from exc


def invalidate_ollama_runtime_cache() -> None:
    with OLLAMA_RUNTIME_CACHE_LOCK:
        for cache_entry in OLLAMA_RUNTIME_CACHE.values():
            cache_entry["expires_at"] = 0.0
            cache_entry["value"] = OLLAMA_CACHE_MISS


def _read_ollama_runtime_cache(key: str) -> Any:
    if OLLAMA_RUNTIME_CACHE_TTL_SEC <= 0:
        return OLLAMA_CACHE_MISS
    now = perf_counter()
    with OLLAMA_RUNTIME_CACHE_LOCK:
        cache_entry = OLLAMA_RUNTIME_CACHE.get(key)
        if not cache_entry:
            return OLLAMA_CACHE_MISS
        if now >= float(cache_entry["expires_at"]):
            return OLLAMA_CACHE_MISS
        value = cache_entry["value"]
    if isinstance(value, dict):
        return value.copy()
    if isinstance(value, list):
        return list(value)
    return value


def _write_ollama_runtime_cache(key: str, value: Any) -> Any:
    if OLLAMA_RUNTIME_CACHE_TTL_SEC <= 0:
        return value
    stored_value = value.copy() if isinstance(value, dict) else list(value) if isinstance(value, list) else value
    with OLLAMA_RUNTIME_CACHE_LOCK:
        OLLAMA_RUNTIME_CACHE[key] = {
            "expires_at": perf_counter() + OLLAMA_RUNTIME_CACHE_TTL_SEC,
            "value": stored_value,
        }
    return value


def _ollama_tags_payload() -> dict[str, Any] | None:
    cached = _read_ollama_runtime_cache("tags_payload")
    if cached is not OLLAMA_CACHE_MISS:
        return cached

    payload: dict[str, Any] | None = None
    try:
        request = UrlRequest(url=f"{OLLAMA_BASE_URL}/api/tags", method="GET")
        with urlopen(request, timeout=4) as response:
            if response.status != 200:
                payload = None
            else:
                body = response.read().decode("utf-8")
                parsed = json.loads(body)
                payload = parsed if isinstance(parsed, dict) else None
    except Exception:
        payload = None

    return _write_ollama_runtime_cache("tags_payload", payload)


def ollama_available() -> bool:
    return _ollama_tags_payload() is not None


def ollama_installed_models() -> list[str]:
    payload = _ollama_tags_payload()
    if not payload:
        return []

    models: list[str] = []
    for item in payload.get("models", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        lowered = name.lower()
        if "embed" in lowered or "embedding" in lowered:
            continue
        models.append(name)
    return models


def _model_speed_rank(model_name: str) -> tuple[float, int, str]:
    lowered = model_name.lower()
    size_match = re.search(r"(\d+(?:\.\d+)?)b", lowered)
    size_score = float(size_match.group(1)) if size_match else 99.0
    mini_bonus = -0.8 if "mini" in lowered else 0.0
    instruct_bonus = -0.15 if "instruct" in lowered else 0.0
    return (size_score + mini_bonus + instruct_bonus, len(model_name), lowered)


def pick_ollama_chat_model(*, prefer_fast: bool = False) -> str:
    global OLLAMA_ACTIVE_MODEL
    if OLLAMA_SPEED_PRESET == "quality":
        OLLAMA_ACTIVE_MODEL = OLLAMA_MODEL
        return OLLAMA_ACTIVE_MODEL

    with OLLAMA_MODEL_PICK_LOCK:
        installed = ollama_installed_models()
        if not installed:
            OLLAMA_ACTIVE_MODEL = OLLAMA_MODEL
            return OLLAMA_ACTIVE_MODEL

        installed_set = set(installed)
        if OLLAMA_SPEED_PRESET == "turbo" or prefer_fast:
            for candidate in OLLAMA_FAST_MODELS:
                if candidate in installed_set:
                    OLLAMA_ACTIVE_MODEL = candidate
                    return OLLAMA_ACTIVE_MODEL

            fastest = sorted(installed, key=_model_speed_rank)[0]
            OLLAMA_ACTIVE_MODEL = fastest
            return OLLAMA_ACTIVE_MODEL

        # balanced
        if OLLAMA_MODEL in installed_set:
            OLLAMA_ACTIVE_MODEL = OLLAMA_MODEL
            return OLLAMA_ACTIVE_MODEL

        OLLAMA_ACTIVE_MODEL = sorted(installed, key=_model_speed_rank)[0]
        return OLLAMA_ACTIVE_MODEL


def get_ollama_turbo_state() -> OllamaTurboResponse:
    installed_fast = OLLAMA_PULL_FAST_MODEL in set(ollama_installed_models())
    with OLLAMA_TURBO_INSTALL_LOCK:
        installed_value = bool(OLLAMA_TURBO_INSTALL_STATE["installed"]) or installed_fast
        return OllamaTurboResponse(
            running=bool(OLLAMA_TURBO_INSTALL_STATE["running"]),
            target_model=str(OLLAMA_TURBO_INSTALL_STATE["target_model"]),
            installed=installed_value,
            detail=str(OLLAMA_TURBO_INSTALL_STATE["detail"]),
        )


def _set_ollama_turbo_state(*, running: bool, installed: bool, detail: str) -> None:
    with OLLAMA_TURBO_INSTALL_LOCK:
        OLLAMA_TURBO_INSTALL_STATE["running"] = running
        OLLAMA_TURBO_INSTALL_STATE["installed"] = installed
        OLLAMA_TURBO_INSTALL_STATE["detail"] = detail
        OLLAMA_TURBO_INSTALL_STATE["target_model"] = OLLAMA_PULL_FAST_MODEL


def start_ollama_turbo_install() -> OllamaTurboResponse:
    with OLLAMA_TURBO_INSTALL_LOCK:
        if OLLAMA_TURBO_INSTALL_STATE["running"]:
            return OllamaTurboResponse(
                running=True,
                target_model=str(OLLAMA_TURBO_INSTALL_STATE["target_model"]),
                installed=bool(OLLAMA_TURBO_INSTALL_STATE["installed"]),
                detail=str(OLLAMA_TURBO_INSTALL_STATE["detail"]),
            )
        OLLAMA_TURBO_INSTALL_STATE["running"] = True
        OLLAMA_TURBO_INSTALL_STATE["installed"] = False
        OLLAMA_TURBO_INSTALL_STATE["detail"] = "Descargando modelo turbo..."
        OLLAMA_TURBO_INSTALL_STATE["target_model"] = OLLAMA_PULL_FAST_MODEL

    def _install_task() -> None:
        try:
            payload = {"model": OLLAMA_PULL_FAST_MODEL, "stream": False}
            http_post_json(
                f"{OLLAMA_BASE_URL}/api/pull",
                payload,
                timeout=max(900, OLLAMA_REQUEST_TIMEOUT),
            )
            invalidate_ollama_runtime_cache()
            pick_ollama_chat_model()
            _set_ollama_turbo_state(
                running=False,
                installed=True,
                detail=f"Modelo turbo listo: {OLLAMA_PULL_FAST_MODEL}",
            )
        except Exception as exc:  # pragma: no cover - network/system dependent
            _set_ollama_turbo_state(
                running=False,
                installed=False,
                detail=f"No se pudo instalar modelo turbo: {exc}",
            )

    Thread(target=_install_task, daemon=True).start()
    return get_ollama_turbo_state()


def ollama_chat_options(for_feedback: bool = False) -> dict[str, float | int]:
    if for_feedback:
        options: dict[str, float | int] = {
            "temperature": 0.2,
            "top_p": 0.9,
            "repeat_penalty": 1.05,
            "num_ctx": OLLAMA_NUM_CTX,
            "num_predict": OLLAMA_FEEDBACK_MAX_TOKENS,
        }
    else:
        chat_ctx = min(OLLAMA_NUM_CTX, 2048)
        options = {
            "temperature": OLLAMA_TEMPERATURE,
            "top_p": OLLAMA_TOP_P,
            "repeat_penalty": OLLAMA_REPEAT_PENALTY,
            "num_ctx": chat_ctx,
            "num_predict": OLLAMA_CHAT_MAX_TOKENS,
        }

    if OLLAMA_NUM_THREAD > 0:
        options["num_thread"] = OLLAMA_NUM_THREAD
    return options


def warmup_ollama_once() -> None:
    global OLLAMA_WARMED
    if OLLAMA_WARMED:
        return
    with OLLAMA_WARMUP_LOCK:
        if OLLAMA_WARMED:
            return
        warmup_model = pick_ollama_chat_model()
        payload = {
            "model": warmup_model,
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "messages": [{"role": "user", "content": "Hallo!"}],
            "options": {"num_predict": 1, "temperature": 0.1, "num_ctx": OLLAMA_NUM_CTX},
        }
        http_post_json(f"{OLLAMA_BASE_URL}/api/chat", payload, timeout=max(120, OLLAMA_REQUEST_TIMEOUT))
        OLLAMA_WARMED = True


def resolve_provider() -> Literal["ollama", "rulebased"]:
    provider = get_provider_preference()

    if provider == "ollama":
        if ollama_available():
            return "ollama"
        return "rulebased"
    if provider == "rulebased":
        return "rulebased"

    if ollama_available():
        return "ollama"
    if ALLOW_RULEBASED_FALLBACK:
        return "rulebased"
    return "rulebased"


def should_block_rulebased_mode() -> bool:
    if ALLOW_RULEBASED_FALLBACK:
        return False
    # If user explicitly asked for rulebased mode, honor it.
    return get_provider_preference() != "rulebased"


def rulebased_block_detail() -> str:
    preferred_model = pick_ollama_chat_model()
    return (
        "No hay un modelo conversacional activo. "
        "Para hablar de cualquier tema con lenguaje natural, inicia Ollama. "
        "Ejecuta iniciar_chatbot.bat (lanzador unico) o inicia 'ollama serve' y asegúrate de que "
        f"el modelo '{preferred_model}' esté disponible."
    )


def build_ollama_messages(
    level: str,
    transcript: list[TranscriptEntryDict],
    max_messages: int = OLLAMA_MAX_HISTORY_MESSAGES,
    include_memory: bool = True,
    constraints: ChatReplyConstraints | None = None,
    coherence: SessionCoherenceDict | None = None,
) -> list[dict[str, str]]:
    constraints = constraints or ChatReplyConstraints()
    trimmed = trim_transcript_for_model(
        transcript,
        max_messages=max_messages,
        max_chars=CHAT_HISTORY_CHAR_BUDGET,
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(level=level)}]
    messages.append({"role": "system", "content": CHAT_RESPONSE_SYSTEM_NOTE})
    messages.append({"role": "system", "content": CHAT_SPOKEN_RESPONSE_SYSTEM_NOTE})
    latest_user_text = next((item["text"] for item in reversed(trimmed) if item["role"] == "user"), "")
    constraint_note = build_chat_constraint_system_note(constraints, latest_user_text)
    if constraint_note:
        messages.append({"role": "system", "content": constraint_note})
    coherence_note = build_chat_coherence_system_note(coherence)
    if coherence_note:
        messages.append({"role": "system", "content": coherence_note})
    messages.append({"role": "system", "content": runtime_datetime_system_note()})
    if include_memory:
        memory_note = learner_memory_system_note()
        if memory_note:
            messages.append({"role": "system", "content": memory_note})
    messages.extend(transcript_to_chat_messages(trimmed))
    return messages


def should_prioritize_fast_ollama_chat(transcript: list[TranscriptEntryDict]) -> bool:
    user_turns = sum(1 for item in transcript if item["role"] == "user")
    if user_turns <= OLLAMA_FAST_TURN_USER_THRESHOLD:
        return True

    last_user_message = next(
        (item["text"].strip() for item in reversed(transcript) if item["role"] == "user" and item["text"].strip()),
        "",
    )
    if not last_user_message:
        return False

    transcript_chars = sum(len(item["text"]) for item in transcript)
    return (
        len(last_user_message) <= OLLAMA_FAST_MESSAGE_CHAR_THRESHOLD
        and transcript_chars <= CHAT_HISTORY_CHAR_BUDGET // 2
    )


def build_chat_provider_attempt_order(
    primary_provider: Literal["ollama", "rulebased"],
) -> list[Literal["ollama", "rulebased"]]:
    preferred_order: dict[str, list[Literal["ollama", "rulebased"]]] = {
        "ollama": ["ollama", "rulebased"],
        "rulebased": ["rulebased"],
    }
    ordered: list[Literal["ollama", "rulebased"]] = []
    for candidate in preferred_order[primary_provider]:
        if candidate not in ordered:
            ordered.append(candidate)
    if primary_provider != "rulebased" and "rulebased" not in ordered:
        ordered.append("rulebased")
    return ordered


def generate_chat_reply(
    *,
    message: str,
    level: str,
    transcript: list[TranscriptEntryDict],
    preferred_provider: Literal["ollama", "rulebased"],
    coherence: SessionCoherenceDict | None = None,
) -> tuple[str, Literal["ollama", "rulebased"], str | None]:
    constraints = extract_chat_reply_constraints(message)
    quick_reply = (
        maybe_direct_question_bundle_reply(message, level, constraints, coherence=coherence)
        or maybe_personal_answer(message, level, constraints, coherence=coherence)
        or maybe_smalltalk_reply(message, level, constraints, coherence=coherence)
    )
    if quick_reply:
        return finalize_assistant_reply(restore_german_text(quick_reply), constraints=constraints), "rulebased", "fast_path"

    errors: list[str] = []
    user_turns = sum(1 for item in transcript if item["role"] == "user")
    for provider_name in build_chat_provider_attempt_order(preferred_provider):
        attempt_started = perf_counter()
        try:
            if provider_name == "ollama":
                if preferred_provider != "ollama" and not ollama_available():
                    raise RuntimeError("Ollama is not reachable.")
                if user_turns <= 1 and not OLLAMA_WARMED:
                    raw_reply = rulebased_reply(
                        user_text=message,
                        level=level,
                        transcript=transcript,
                        constraints=constraints,
                        coherence=coherence,
                    )
                    provider_name = "rulebased"
                else:
                    raw_reply = chat_with_ollama(level=level, transcript=transcript, constraints=constraints, coherence=coherence)
            else:
                raw_reply = rulebased_reply(
                    user_text=message,
                    level=level,
                    transcript=transcript,
                    constraints=constraints,
                    coherence=coherence,
                )

            final_reply = finalize_assistant_reply(raw_reply, constraints=constraints)
            issue = detect_assistant_reply_issue(final_reply, message)
            if issue:
                raise RuntimeError(f"reply quality issue: {issue}")

            latency_ms = int((perf_counter() - attempt_started) * 1000)
            logger.info(
                "chat.provider.ok provider=%s preferred=%s turns=%s latency_ms=%s",
                provider_name,
                preferred_provider,
                user_turns,
                latency_ms,
            )
            degraded_reason = None
            if provider_name != preferred_provider:
                degraded_reason = errors[-1] if errors else "fallback"
            return final_reply, provider_name, degraded_reason
        except RuntimeError as exc:
            latency_ms = int((perf_counter() - attempt_started) * 1000)
            errors.append(f"{provider_name}:{exc}")
            logger.warning(
                "chat.provider.failed provider=%s preferred=%s turns=%s latency_ms=%s reason=%s",
                provider_name,
                preferred_provider,
                user_turns,
                latency_ms,
                exc,
            )

    fallback_reply = finalize_assistant_reply(
        rulebased_reply(
            user_text=message,
            level=level,
            transcript=transcript,
            constraints=constraints,
            coherence=coherence,
        ),
        constraints=constraints,
    )
    return fallback_reply, "rulebased", errors[-1] if errors else "fallback"


def chat_with_ollama(
    level: str,
    transcript: list[TranscriptEntryDict],
    constraints: ChatReplyConstraints | None = None,
    coherence: SessionCoherenceDict | None = None,
) -> str:
    prefer_fast = should_prioritize_fast_ollama_chat(transcript)
    chat_model = pick_ollama_chat_model(prefer_fast=prefer_fast)
    is_turbo = OLLAMA_SPEED_PRESET == "turbo" or prefer_fast
    options = ollama_chat_options(for_feedback=False)
    if is_turbo:
        options["num_predict"] = min(
            int(options.get("num_predict", OLLAMA_CHAT_MAX_TOKENS)),
            48,
        )
        options["num_ctx"] = min(
            int(options.get("num_ctx", OLLAMA_NUM_CTX)),
            1280,
        )
        options["temperature"] = min(
            float(options.get("temperature", OLLAMA_TEMPERATURE)),
            0.45,
        )
        options["top_p"] = min(float(options.get("top_p", OLLAMA_TOP_P)), 0.9)

    message_budget = 4 if is_turbo else OLLAMA_MAX_HISTORY_MESSAGES
    payload = {
        "model": chat_model,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": options,
        "messages": build_ollama_messages(
            level=level,
            transcript=transcript,
            max_messages=min(OLLAMA_MAX_HISTORY_MESSAGES, message_budget),
            include_memory=not is_turbo,
            constraints=constraints,
            coherence=coherence,
        ),
    }
    logger.info(
        "chat.ollama.request model=%s fast_profile=%s user_turns=%s context_messages=%s",
        chat_model,
        is_turbo,
        sum(1 for item in transcript if item["role"] == "user"),
        len(payload["messages"]),
    )
    response = http_post_json(
        f"{OLLAMA_BASE_URL}/api/chat",
        payload,
        timeout=OLLAMA_CHAT_TIMEOUT,
    )
    message = response.get("message", {})
    content = str(message.get("content", "")).strip()
    if not content:
        raise RuntimeError("Ollama returned an empty response.")
    return content


def open_ollama_chat_stream_response(
    level: str,
    transcript: list[TranscriptEntryDict],
    constraints: ChatReplyConstraints | None = None,
    coherence: SessionCoherenceDict | None = None,
) -> Any:
    prefer_fast = should_prioritize_fast_ollama_chat(transcript)
    chat_model = pick_ollama_chat_model(prefer_fast=prefer_fast)
    is_turbo = OLLAMA_SPEED_PRESET == "turbo" or prefer_fast
    options = ollama_chat_options(for_feedback=False)
    if is_turbo:
        options["num_predict"] = min(
            int(options.get("num_predict", OLLAMA_CHAT_MAX_TOKENS)),
            48,
        )
        options["num_ctx"] = min(
            int(options.get("num_ctx", OLLAMA_NUM_CTX)),
            1280,
        )
        options["temperature"] = min(
            float(options.get("temperature", OLLAMA_TEMPERATURE)),
            0.45,
        )
        options["top_p"] = min(float(options.get("top_p", OLLAMA_TOP_P)), 0.9)

    message_budget = 4 if is_turbo else OLLAMA_MAX_HISTORY_MESSAGES
    payload = {
        "model": chat_model,
        "stream": True,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": options,
        "messages": build_ollama_messages(
            level=level,
            transcript=transcript,
            max_messages=min(OLLAMA_MAX_HISTORY_MESSAGES, message_budget),
            include_memory=not is_turbo,
            constraints=constraints,
            coherence=coherence,
        ),
    }
    logger.info(
        "chat.ollama.stream.request model=%s fast_profile=%s user_turns=%s context_messages=%s",
        chat_model,
        is_turbo,
        sum(1 for item in transcript if item["role"] == "user"),
        len(payload["messages"]),
    )
    data = json.dumps(payload).encode("utf-8")
    request = UrlRequest(
        url=f"{OLLAMA_BASE_URL}/api/chat",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        return urlopen(request, timeout=OLLAMA_CHAT_TIMEOUT)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError(
            f"Ollama timeout after {OLLAMA_CHAT_TIMEOUT}s. The model may still be loading. Try again."
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"Ollama not reachable: {exc.reason}") from exc
    except OSError as exc:
        raise RuntimeError(f"Ollama OS/network error: {exc}") from exc


def iter_ollama_chat_stream(response: Any) -> Any:
    try:
        while True:
            raw_line = response.readline()
            if not raw_line:
                break
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Ollama returned invalid streaming JSON.") from exc
            yield payload
    finally:
        try:
            response.close()
        except Exception:
            pass


def resolve_chat_conversation_state(
    conversation_id: str | None,
    level: str,
    persona_key: str | None = None,
) -> tuple[str, SessionState]:
    conv_id = conversation_id
    if conv_id:
        existing = get_session_snapshot(conv_id)
        if existing and existing["level"] != level:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"This conversation uses level {existing['level']}. "
                    "Start a new conversation to change level."
                ),
            )
    if not conv_id:
        conv_id = uuid4().hex
    if not conv_id:
        raise HTTPException(status_code=500, detail="Conversation ID was not generated.")
    ensure_session(conv_id, level, requested_persona_key=persona_key)
    session = get_session_snapshot(conv_id)
    if not session:
        raise HTTPException(status_code=500, detail="Conversation state is unavailable.")
    return conv_id, session


def build_working_chat_transcript(
    session: SessionState,
    *,
    message: str,
) -> list[TranscriptEntryDict]:
    working_transcript = get_active_transcript(session)
    clean_message = str(message or "").strip()
    if clean_message:
        preview_timestamp = utc_now_iso()
        working_transcript.append(
            {
                "id": _new_transcript_entry_id(),
                "role": "user",
                "text": clean_message,
                "timestamp": preview_timestamp,
                "created_at": preview_timestamp,
                "status": "active",
                "reply_to_id": None,
                "version_group_id": "working-preview",
                "version_index": 1,
                "edited_from_id": None,
                "invalidated_by_id": None,
                "meta": {"source": "working"},
            }
        )
    return working_transcript


def transcript_has_completed_assistant_turn(transcript: list[TranscriptEntryDict]) -> bool:
    return any(
        item.get("role") == "assistant"
        and item.get("status", "active") == "active"
        and str(item.get("text", "")).strip()
        for item in transcript
    )


def commit_streamed_tutor_turn(
    *,
    conversation_id: str,
    level: str,
    message: str,
    reply: str,
) -> None:
    clean_message = str(message or "").strip()
    clean_reply = finalize_assistant_reply(str(reply or "").strip())
    if not clean_message or not clean_reply:
        raise HTTPException(status_code=400, detail="Message and reply are required to commit a streamed turn.")

    session = get_session_snapshot(conversation_id)
    if not session:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    if _safe_level(session["level"]) != _safe_level(level):
        raise HTTPException(
            status_code=409,
            detail=(
                f"This conversation uses level {session['level']}. "
                "Start a new conversation to change level."
            ),
        )

    transcript = get_active_transcript(session)
    if len(transcript) >= 2:
        previous_user = transcript[-2]
        previous_assistant = transcript[-1]
        if (
            previous_user.get("role") == "user"
            and previous_assistant.get("role") == "assistant"
            and str(previous_user.get("text", "")).strip() == clean_message
            and str(previous_assistant.get("text", "")).strip() == clean_reply
        ):
            return

    user_entry = append_transcript(
        conversation_id,
        level,
        "user",
        clean_message,
        meta_source="streamed",
    )
    if not user_entry:
        raise HTTPException(status_code=500, detail="Could not store streamed user message.")
    assistant_entry = append_transcript(
        conversation_id,
        level,
        "assistant",
        clean_reply,
        reply_to_id=str(user_entry.get("id") or ""),
        version_group_id=_clean_optional_str(user_entry.get("version_group_id")),
        version_index=int(user_entry.get("version_index") or 1),
        meta_source="streamed",
    )
    if not assistant_entry:
        raise HTTPException(status_code=500, detail="Could not store streamed assistant reply.")
    rebuild_session_coherence(conversation_id)


def build_mutated_transcript_preview(
    session: SessionState,
    *,
    target_entry_id: str,
    replacement_text: str,
    replacement_entry_id: str,
    version_group_id: str,
    version_index: int,
    edited_from_id: str | None,
    meta_source: str,
    created_at: str,
) -> list[TranscriptEntryDict]:
    active_transcript = get_active_transcript(session)
    preview: list[TranscriptEntryDict] = []
    replacement_added = False
    for item in active_transcript:
        if item.get("id") == target_entry_id:
            preview.append(
                {
                    "id": replacement_entry_id,
                    "role": "user",
                    "text": replacement_text,
                    "timestamp": created_at,
                    "created_at": created_at,
                    "status": "active",
                    "reply_to_id": None,
                    "version_group_id": version_group_id,
                    "version_index": version_index,
                    "edited_from_id": _clean_optional_str(edited_from_id),
                    "invalidated_by_id": None,
                    "meta": {"source": meta_source},
                }
            )
            replacement_added = True
            break
        preview.append(_copy_transcript_entry(item))
    if not replacement_added:
        raise HTTPException(status_code=404, detail="Active user message not found in canonical transcript.")
    return preview


def generate_regenerated_chat_reply(
    *,
    message: str,
    level: str,
    transcript: list[TranscriptEntryDict],
    coherence: SessionCoherenceDict | None = None,
) -> str:
    preferred_provider = resolve_provider()
    if preferred_provider == "rulebased" and should_block_rulebased_mode():
        raise HTTPException(status_code=503, detail=rulebased_block_detail())
    try:
        assistant_reply, _, _ = generate_chat_reply(
            message=message,
            level=level,
            transcript=transcript,
            preferred_provider=preferred_provider,
            coherence=coherence,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    constraints = extract_chat_reply_constraints(message)
    final_reply = finalize_assistant_reply(assistant_reply, constraints=constraints)
    if not final_reply:
        raise HTTPException(status_code=502, detail="Regenerated assistant reply was empty.")
    return final_reply


def mutate_user_message_version(
    *,
    conversation_id: str,
    entry_id: str,
    replacement_text: str,
    source: Literal["edited", "restored"],
    restore_from_entry_id: str | None = None,
) -> TranscriptMutationResponse:
    snapshot = get_session_snapshot(conversation_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    active_target = find_transcript_entry(snapshot, entry_id, role="user")
    if not active_target or active_target.get("status", "active") != "active":
        raise HTTPException(status_code=400, detail="Only active user messages can be edited or restored.")

    version_group_id = _clean_optional_str(active_target.get("version_group_id"))
    if not version_group_id:
        raise HTTPException(status_code=500, detail="User message is missing version metadata.")

    current_active = get_active_user_entry_for_version_group(snapshot, version_group_id)
    if not current_active or current_active.get("id") != active_target.get("id"):
        raise HTTPException(status_code=409, detail="Conversation branch changed. Reload the transcript and try again.")

    if source == "restored":
        restore_source = find_transcript_entry(snapshot, restore_from_entry_id or "", role="user")
        if not restore_source:
            raise HTTPException(status_code=404, detail="Restore source version not found.")
        if restore_source.get("version_group_id") != version_group_id:
            raise HTTPException(status_code=400, detail="Restore source must belong to the same message version group.")
        if restore_source.get("id") == active_target.get("id"):
            raise HTTPException(status_code=400, detail="Selected version is already active.")
        clean_text = str(restore_source.get("text", "")).strip()
    else:
        clean_text = str(replacement_text or "").strip()

    if not clean_text:
        raise HTTPException(status_code=400, detail="Edited message text is required.")
    if clean_text == str(active_target.get("text", "")).strip():
        raise HTTPException(status_code=400, detail="Edited text matches the current active version.")

    versions = list_user_versions(snapshot, version_group_id)
    next_version_index = max((int(item.get("version_index") or 1) for item in versions), default=1) + 1
    new_user_entry_id = _new_transcript_entry_id()
    preview_created_at = utc_now_iso()
    preview_transcript = build_mutated_transcript_preview(
        snapshot,
        target_entry_id=str(active_target.get("id") or ""),
        replacement_text=clean_text,
        replacement_entry_id=new_user_entry_id,
        version_group_id=version_group_id,
        version_index=next_version_index,
        edited_from_id=str(active_target.get("id") or ""),
        meta_source=source,
        created_at=preview_created_at,
    )
    preview_coherence = build_preview_coherence(snapshot, preview_transcript)
    regenerated_reply = generate_regenerated_chat_reply(
        message=clean_text,
        level=snapshot["level"],
        transcript=preview_transcript,
        coherence=preview_coherence,
    )

    assistant_entry_id = _new_transcript_entry_id()
    invalidated_entry_ids: list[str] = []
    with SESSIONS_LOCK:
        live_session = SESSIONS.get(conversation_id)
        if not live_session:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        live_target = find_transcript_entry(live_session, entry_id, role="user")
        if (
            not live_target
            or live_target.get("status", "active") != "active"
            or str(live_target.get("text", "")).strip() != str(active_target.get("text", "")).strip()
        ):
            raise HTTPException(status_code=409, detail="Conversation changed. Reload the transcript and try again.")
        live_current_active = get_active_user_entry_for_version_group(live_session, version_group_id)
        if not live_current_active or live_current_active.get("id") != live_target.get("id"):
            raise HTTPException(status_code=409, detail="Conversation branch changed. Reload the transcript and try again.")

        mark_transcript_entry_status(live_target, status="superseded", invalidated_by_id=new_user_entry_id)
        if live_target.get("id"):
            invalidated_entry_ids.append(str(live_target["id"]))

        previous_assistant = find_active_assistant_reply(live_session, str(live_target.get("id") or ""))
        if previous_assistant:
            mark_transcript_entry_status(previous_assistant, status="outdated", invalidated_by_id=new_user_entry_id)
            if previous_assistant.get("id"):
                invalidated_entry_ids.append(str(previous_assistant["id"]))
            invalidated_entry_ids.extend(
                invalidate_active_entries_after(
                    live_session,
                    start_entry_id=str(previous_assistant.get("id") or ""),
                    invalidated_by_id=new_user_entry_id,
                )
            )
        else:
            invalidated_entry_ids.extend(
                invalidate_active_entries_after(
                    live_session,
                    start_entry_id=str(live_target.get("id") or ""),
                    invalidated_by_id=new_user_entry_id,
                )
            )

        new_user_entry = _build_transcript_entry_record(
            live_session,
            role="user",
            text=clean_text,
            entry_id=new_user_entry_id,
            version_group_id=version_group_id,
            version_index=next_version_index,
            edited_from_id=str(live_target.get("id") or ""),
            status="active",
            meta_source=source,
            created_at=preview_created_at,
        )
        _append_transcript_entry_locked(live_session, new_user_entry)

        assistant_entry = _build_transcript_entry_record(
            live_session,
            role="assistant",
            text=regenerated_reply,
            entry_id=assistant_entry_id,
            reply_to_id=new_user_entry_id,
            version_group_id=version_group_id,
            version_index=next_version_index,
            status="active",
            meta_source="regenerated",
        )
        _append_transcript_entry_locked(live_session, assistant_entry)
        ensure_session_coherence_locked(live_session, rebuild=True)
        active_transcript = get_active_transcript(live_session)

    schedule_state_persist()
    deduped_invalidated = list(dict.fromkeys(item for item in invalidated_entry_ids if item))
    return TranscriptMutationResponse(
        conversation_id=conversation_id,
        level=snapshot["level"],
        entry_id=new_user_entry_id,
        assistant_entry_id=assistant_entry_id,
        invalidated_entry_ids=deduped_invalidated,
        transcript=build_transcript_response_entries(active_transcript),
    )


def build_chat_auxiliary_feedback(
    *,
    message: str,
    mode: str,
) -> tuple[str | None, list[str]]:
    correction = None
    tips: list[str] = []
    if mode == "fluidez":
        return correction, tips

    corrected_input, issues = detect_generic_errors(
        message,
        min_words=8 if mode in {"goethe_sprechen", "roleplay"} else 0,
        require_question=mode == "roleplay",
    )
    if issues:
        correction_parts = [f"{issue.label}: {issue.description}" for issue in issues[:2]]
        correction = " ".join(correction_parts)
        tips = [issue.recommendation for issue in issues[:2]]
    elif mode == "goethe_sprechen":
        correction = f"Version pulida sugerida: {corrected_input}"
        tips = [
            "Responde en 2-4 frases con una idea central y un ejemplo.",
            "Añade un conector y una propuesta concreta para sonar a examen.",
        ]
    elif mode == "roleplay":
        tips = [
            "Incluye una reaccion directa y una pregunta corta.",
            "Cierra con una propuesta o solucion concreta.",
        ]
    else:
        tips = [
            "Reescribe tu ultimo mensaje con puntuacion clara.",
            "Usa un conector como `weil`, `deshalb` o `außerdem`.",
        ]
    return correction, tips


def encode_tutor_stream_event(event_type: str, **payload: Any) -> str:
    return json.dumps({"type": event_type, **payload}, ensure_ascii=False) + "\n"


def finish_with_ollama(level: str, transcript: list[TranscriptEntryDict]) -> str:
    prompt = FINAL_FEEDBACK_PROMPT.format(level=level, transcript=transcript_to_prompt(transcript))
    feedback_model = pick_ollama_chat_model() if OLLAMA_SPEED_PRESET == "turbo" else OLLAMA_MODEL
    payload = {
        "model": feedback_model,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": ollama_chat_options(for_feedback=True),
        "messages": [
            {"role": "system", "content": "Responde en espanol claro y estructurado."},
            {"role": "user", "content": prompt},
        ],
    }
    response = http_post_json(f"{OLLAMA_BASE_URL}/api/chat", payload)
    message = response.get("message", {})
    content = str(message.get("content", "")).strip()
    if not content:
        raise RuntimeError("Ollama returned empty feedback.")
    return content


def analyze_monologue_with_ollama(
    raw_text: str,
    normalized_text: str,
    heuristic_notes: str,
    level: str,
    goal_level: str,
    estimated_level: str,
) -> str:
    prompt = MONOLOGUE_FEEDBACK_PROMPT.format(
        level=level,
        goal_level=goal_level,
        estimated_level=estimated_level,
        raw_monologue=raw_text,
        normalized_monologue=normalized_text,
        heuristic_notes=heuristic_notes,
    )
    analysis_model = pick_ollama_chat_model() if OLLAMA_SPEED_PRESET == "turbo" else OLLAMA_MODEL
    payload = {
        "model": analysis_model,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": ollama_chat_options(for_feedback=True),
        "messages": [
            {"role": "system", "content": "Responde en espanol claro, estructurado y accionable."},
            {"role": "user", "content": prompt},
        ],
    }
    response = http_post_json(f"{OLLAMA_BASE_URL}/api/chat", payload)
    message = response.get("message", {})
    content = str(message.get("content", "")).strip()
    if not content:
        raise RuntimeError("Ollama returned empty monologue analysis.")
    return content


@asynccontextmanager
async def app_lifespan(_: FastAPI):
    load_state_from_disk()
    init_learning_db()
    ensure_local_user()
    if resolve_provider() == "ollama" and OLLAMA_ENABLE_STARTUP_WARMUP:

        def _warmup_task() -> None:
            try:
                warmup_ollama_once()
            except Exception:
                # Warmup is best effort; normal chat path will still work.
                return

        Timer(OLLAMA_STARTUP_WARMUP_DELAY_SEC, _warmup_task).start()
    yield
    flush_pending_state_persist()


app = FastAPI(title="German Speaking Coach API", lifespan=app_lifespan)

allowed_origins = parse_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials="*" not in allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(learning_router)

@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    if not INDEX_FILE.exists():
        raise HTTPException(status_code=500, detail="UI file missing: static/index.html")
    return FileResponse(
        INDEX_FILE,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/local-ca.crt", include_in_schema=False)
def local_ca_certificate() -> FileResponse:
    if not LOCAL_CA_CERT_PATH.exists():
        raise HTTPException(status_code=404, detail="Local HTTPS certificate is not available yet.")
    return FileResponse(
        LOCAL_CA_CERT_PATH,
        media_type="application/x-x509-ca-cert",
        filename="chatbot-local-ca.crt",
        headers={"Cache-Control": "no-store, max-age=0"},
    )

@app.get("/config", response_model=RuntimeConfigResponse)
def runtime_config() -> RuntimeConfigResponse:
    provider = resolve_provider()
    transcribe_provider = resolve_transcribe_provider()
    active_model = pick_ollama_chat_model() if provider == "ollama" else None
    tutor_tts_status = get_tutor_tts_status()
    return RuntimeConfigResponse(
        provider=provider,
        transcribe_provider=transcribe_provider,
        server_transcribe=transcribe_provider != "none",
        tutor_streaming_enabled=TUTOR_STREAMING_ENABLED,
        tutor_local_tts_available=tutor_tts_status.available,
        tutor_tts_fallback=tutor_tts_status.fallback if tutor_tts_status.fallback in {"browser", "none"} else "browser",
        tutor_tts_voice_label=tutor_tts_status.voice_label,
        llm_required=provider == "rulebased" and should_block_rulebased_mode(),
        active_model=active_model,
        transcribe_model=current_transcribe_model_label(transcribe_provider),
        speed_profile=OLLAMA_SPEED_PRESET if provider == "ollama" else None,
        chat_timeout_ms=FRONTEND_CHAT_TIMEOUT_MS,
        transcribe_timeout_ms=FRONTEND_TRANSCRIBE_TIMEOUT_MS,
    )


@app.get("/ollama/turbo", response_model=OllamaTurboResponse)
def ollama_turbo_status() -> OllamaTurboResponse:
    return get_ollama_turbo_state()


@app.post("/ollama/turbo", response_model=OllamaTurboResponse)
def ollama_turbo_install() -> OllamaTurboResponse:
    if resolve_provider() != "ollama":
        raise HTTPException(status_code=400, detail="Turbo install solo aplica en modo Ollama.")
    return start_ollama_turbo_install()


@app.get("/conversations", response_model=list[ConversationSummary])
def conversations() -> list[ConversationSummary]:
    return list_conversation_summaries(limit=300)


@app.get("/api/chat/history", response_model=list[ConversationSummary])
def api_chat_history() -> list[ConversationSummary]:
    return list_conversation_summaries(limit=300)


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    preferred_provider = resolve_provider()
    if preferred_provider == "rulebased" and should_block_rulebased_mode():
        raise HTTPException(status_code=503, detail=rulebased_block_detail())
    request_started = perf_counter()
    conv_id, session = resolve_chat_conversation_state(req.conversation_id, req.level, req.persona_key)
    working_transcript = build_working_chat_transcript(session, message=req.message)
    preview_coherence = build_preview_coherence(session, working_transcript, requested_persona_key=req.persona_key)
    constraints = extract_chat_reply_constraints(req.message)

    try:
        assistant_reply, provider_used, degraded_reason = generate_chat_reply(
            message=req.message,
            level=req.level,
            transcript=working_transcript,
            preferred_provider=preferred_provider,
            coherence=preview_coherence,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not assistant_reply:
        assistant_reply = (
            "Entschuldigung, ich habe dich nicht gut verstanden. "
            "Kannst du es bitte noch einmal sagen?"
        )
    assistant_reply = finalize_assistant_reply(assistant_reply, constraints=constraints)

    user_entry = append_transcript(conv_id, req.level, "user", req.message, meta_source="blocking")
    if not user_entry:
        raise HTTPException(status_code=500, detail="Could not store user message.")
    assistant_entry = append_transcript(
        conv_id,
        req.level,
        "assistant",
        assistant_reply,
        reply_to_id=str(user_entry.get("id") or ""),
        version_group_id=_clean_optional_str(user_entry.get("version_group_id")),
        version_index=int(user_entry.get("version_index") or 1),
        meta_source="blocking",
    )
    if not assistant_entry:
        raise HTTPException(status_code=500, detail="Could not store assistant reply.")
    rebuild_session_coherence(conv_id)
    total_ms = int((perf_counter() - request_started) * 1000)
    logger.info(
        "chat.complete conversation=%s preferred=%s used=%s turns=%s total_ms=%s degraded=%s",
        conv_id[:8],
        preferred_provider,
        provider_used,
        sum(1 for item in working_transcript if item["role"] == "user"),
        total_ms,
        degraded_reason or "-",
    )
    return ChatResponse(reply=assistant_reply, conversation_id=conv_id)


@app.post("/api/chat", response_model=ApiChatResponse)
def api_chat(req: ApiChatRequest) -> ApiChatResponse:
    legacy_response = chat(
        ChatRequest(
            message=req.message,
            conversation_id=req.conversation_id,
            level=req.level,
            persona_key=req.persona_key,
        )
    )
    correction, tips = build_chat_auxiliary_feedback(message=req.message, mode=req.mode)
    return ApiChatResponse(
        reply=legacy_response.reply,
        conversation_id=legacy_response.conversation_id,
        mode=req.mode,
        correction=correction,
        tips=tips,
    )


@app.post("/api/tutor/chat/stream")
async def api_tutor_chat_stream(req: TutorStreamRequest, request: FastAPIRequest) -> StreamingResponse:
    preferred_provider = resolve_provider()
    if preferred_provider == "rulebased" and should_block_rulebased_mode():
        raise HTTPException(status_code=503, detail=rulebased_block_detail())

    conv_id, session = resolve_chat_conversation_state(req.conversation_id, req.level, req.persona_key)
    working_transcript = build_working_chat_transcript(session, message=req.message)
    preview_coherence = build_preview_coherence(session, working_transcript, requested_persona_key=req.persona_key)
    constraints = extract_chat_reply_constraints(req.message)

    async def stream() -> Any:
        request_started = perf_counter()
        reply_chunks: list[str] = []
        emitted_authoritative_sentences: list[str] = []
        provider_used: Literal["ollama", "rulebased"] = "rulebased"
        degraded_reason: str | None = None
        correction: str | None = None
        tips: list[str] = []
        stream_started = False
        completed_normally = False

        async def client_disconnected() -> bool:
            return await request.is_disconnected()

        def log_stream_interrupted(stage: str) -> None:
            logger.info(
                "chat.stream.interrupted conversation=%s preferred=%s used=%s stage=%s streamed=%s",
                conv_id[:8],
                preferred_provider,
                provider_used,
                stage,
                stream_started,
            )

        try:
            if await client_disconnected():
                log_stream_interrupted("before_session")
                return
            yield encode_tutor_stream_event("session", conversation_id=conv_id)
            if await client_disconnected():
                log_stream_interrupted("after_session")
                return
            yield encode_tutor_stream_event("state", state="thinking")
            if await client_disconnected():
                log_stream_interrupted("after_thinking")
                return

            quick_reply = (
                maybe_direct_question_bundle_reply(req.message, req.level, constraints, coherence=preview_coherence)
                or maybe_personal_answer(req.message, req.level, constraints, coherence=preview_coherence)
                or maybe_smalltalk_reply(req.message, req.level, constraints, coherence=preview_coherence)
            )
            if quick_reply:
                provider_used = "rulebased"
                final_reply = finalize_assistant_reply(restore_german_text(quick_reply), constraints=constraints)
            elif preferred_provider != "ollama":
                provider_used = "rulebased"
                final_reply = finalize_assistant_reply(
                    rulebased_reply(
                        user_text=req.message,
                        level=req.level,
                        transcript=working_transcript,
                        constraints=constraints,
                        coherence=preview_coherence,
                    ),
                    constraints=constraints,
                )
            else:
                user_turns = sum(1 for item in working_transcript if item["role"] == "user")
                if user_turns <= 1 and not OLLAMA_WARMED:
                    provider_used = "rulebased"
                    degraded_reason = "ollama:cold_start_rulebased_fast_path"
                    final_reply = finalize_assistant_reply(
                        rulebased_reply(
                            user_text=req.message,
                            level=req.level,
                            transcript=working_transcript,
                            constraints=constraints,
                            coherence=preview_coherence,
                        ),
                        constraints=constraints,
                    )
                else:
                    provider_used = "ollama"
                    try:
                        try:
                            response = open_ollama_chat_stream_response(
                                req.level,
                                working_transcript,
                                constraints=constraints,
                                coherence=preview_coherence,
                            )
                        except TypeError as exc:
                            if "unexpected keyword argument 'coherence'" not in str(exc):
                                raise
                            response = open_ollama_chat_stream_response(
                                req.level,
                                working_transcript,
                                constraints=constraints,
                            )
                    except RuntimeError as exc:
                        provider_used = "rulebased"
                        degraded_reason = f"ollama:{exc}"
                        final_reply = finalize_assistant_reply(
                            rulebased_reply(
                                user_text=req.message,
                                level=req.level,
                                transcript=working_transcript,
                                constraints=constraints,
                                coherence=preview_coherence,
                            ),
                            constraints=constraints,
                        )
                    else:
                        with response:
                            for payload in iter_ollama_chat_stream(response):
                                if await client_disconnected():
                                    log_stream_interrupted("during_model_stream")
                                    return
                                message_payload = payload.get("message", {})
                                chunk_text = str(message_payload.get("content", "") or "")
                                if chunk_text:
                                    if not stream_started:
                                        stream_started = True
                                        yield encode_tutor_stream_event("state", state="streaming")
                                        if await client_disconnected():
                                            log_stream_interrupted("after_streaming_state")
                                            return
                                    reply_chunks.append(chunk_text)
                                    yield encode_tutor_stream_event("delta", text=chunk_text)
                                    authoritative_sentences = split_complete_assistant_sentences("".join(reply_chunks).strip(), constraints=constraints)
                                    if emitted_authoritative_sentences and (
                                        authoritative_sentences[: len(emitted_authoritative_sentences)] != emitted_authoritative_sentences
                                    ):
                                        authoritative_sentences = emitted_authoritative_sentences
                                    for sentence_index, sentence_text in enumerate(
                                        authoritative_sentences[len(emitted_authoritative_sentences):],
                                        start=len(emitted_authoritative_sentences),
                                    ):
                                        emitted_authoritative_sentences.append(sentence_text)
                                        yield encode_tutor_stream_event(
                                            "sentence",
                                            text=sentence_text,
                                            sentence_index=sentence_index,
                                        )
                                        if await client_disconnected():
                                            log_stream_interrupted("after_sentence_event")
                                            return
                        final_reply = finalize_assistant_reply("".join(reply_chunks).strip(), constraints=constraints)
                        if not final_reply:
                            raise RuntimeError("Ollama returned an empty streamed response.")

            if await client_disconnected():
                log_stream_interrupted("before_final_state")
                return
            if not stream_started:
                stream_started = True
                yield encode_tutor_stream_event("state", state="streaming")
                if await client_disconnected():
                    log_stream_interrupted("after_final_only_streaming_state")
                    return

            correction, tips = build_chat_auxiliary_feedback(message=req.message, mode=req.mode)
            if await client_disconnected():
                log_stream_interrupted("before_final")
                return

            yield encode_tutor_stream_event("final", text=final_reply, provider=provider_used)
            if correction:
                yield encode_tutor_stream_event("correction", text=correction)
            if tips:
                yield encode_tutor_stream_event("tips", items=tips)

            completed_normally = True
            total_ms = int((perf_counter() - request_started) * 1000)
            logger.info(
                "chat.stream.complete conversation=%s preferred=%s used=%s turns=%s total_ms=%s degraded=%s streamed=%s",
                conv_id[:8],
                preferred_provider,
                provider_used,
                sum(1 for item in working_transcript if item["role"] == "user"),
                total_ms,
                degraded_reason or "-",
                stream_started,
            )
            yield encode_tutor_stream_event(
                "done",
                conversation_id=conv_id,
                provider=provider_used,
                degraded_reason=degraded_reason,
            )
        except GeneratorExit:
            return
        except asyncio.CancelledError:
            return
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning(
                "chat.stream.failed conversation=%s preferred=%s used=%s streamed=%s completed=%s reason=%s",
                conv_id[:8],
                preferred_provider,
                provider_used,
                stream_started,
                completed_normally,
                exc,
            )
            if completed_normally:
                return
            yield encode_tutor_stream_event("error", detail=str(exc))

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@app.post("/api/tutor/chat/commit")
def api_tutor_chat_commit(req: TutorStreamCommitRequest) -> dict[str, Any]:
    commit_streamed_tutor_turn(
        conversation_id=req.conversation_id,
        level=req.level,
        message=req.message,
        reply=req.reply,
    )
    return {"conversation_id": req.conversation_id, "committed": True}


@app.post("/api/tutor/tts")
def api_tutor_tts(req: TutorTtsRequest) -> Response:
    request_started = perf_counter()
    status = get_tutor_tts_status(req.persona_key)
    if not status.available:
        raise HTTPException(status_code=503, detail=status.detail or "Local Tutor TTS is not available.")

    try:
        audio_bytes, normalized_text = synthesize_tutor_tts(req.text, persona_key=req.persona_key)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    logger.info(
        "tutor.tts.complete turn=%s sentence=%s persona=%s chars=%s latency_ms=%s",
        (req.turn_id or "-")[:16],
        req.sentence_index,
        _normalize_tutor_persona_key(req.persona_key) or "-",
        len(normalized_text),
        int((perf_counter() - request_started) * 1000),
    )

    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "X-Tutor-Tts-Provider": status.provider,
            "X-Tutor-Tts-Voice": status.voice_label or "",
            "X-Tutor-Tts-Voice-Source": status.voice_source or "",
        },
    )


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    audio: UploadFile = File(...),
    language: str = Form("de"),
) -> TranscribeResponse:
    request_started = perf_counter()
    transcribe_provider = resolve_transcribe_provider()
    if transcribe_provider == "none":
        raise HTTPException(
            status_code=503,
            detail=(
                "Server transcription is not available. "
                "Install local dependencies with 'pip install -r requirements.txt' or use browser dictation."
            ),
        )

    content_type = audio.content_type or "application/octet-stream"
    if not content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be audio.")

    audio_bytes = await audio.read()
    await audio.close()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty.")

    filename = audio.filename or "speech.webm"
    try:
        text = transcribe_with_local_model(
            audio_bytes=audio_bytes,
            filename=filename,
            content_type=content_type,
            language=language,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not text:
        raise HTTPException(status_code=422, detail="No speech detected in audio.")

    logger.info(
        "transcribe.complete provider=%s model=%s bytes=%s language=%s latency_ms=%s",
        transcribe_provider,
        current_transcribe_model_label(transcribe_provider) or "-",
        len(audio_bytes),
        language,
        int((perf_counter() - request_started) * 1000),
    )

    return TranscribeResponse(text=text)


@app.post("/monologue/analyze", response_model=MonologueAnalyzeResponse)
def monologue_analyze(req: MonologueAnalyzeRequest) -> MonologueAnalyzeResponse:
    text = " ".join(req.text.strip().split())
    if len(text) < 20:
        raise HTTPException(status_code=400, detail="El monologo es demasiado corto para analizar.")

    normalized_text = autopunctuate_monologue_text(text)
    heuristic_issues = detect_monologue_issues(raw_text=text, normalized_text=normalized_text)
    heuristic_notes = build_monologue_heuristic_notes(
        raw_text=text,
        normalized_text=normalized_text,
        issues=heuristic_issues,
    )
    estimated_level = estimate_level_from_text(text=text, declared_level=req.level)
    provider = resolve_provider()

    if provider == "ollama":
        try:
            feedback = analyze_monologue_with_ollama(
                raw_text=text,
                normalized_text=normalized_text,
                heuristic_notes=heuristic_notes,
                level=req.level,
                goal_level=req.goal_level,
                estimated_level=estimated_level,
            )
        except RuntimeError:
            feedback = rulebased_monologue_feedback(
                text=text,
                level=req.level,
                goal_level=req.goal_level,
                estimated_level=estimated_level,
            )
    else:
        feedback = rulebased_monologue_feedback(
            text=text,
            level=req.level,
            goal_level=req.goal_level,
            estimated_level=estimated_level,
        )

    if not feedback:
        feedback = rulebased_monologue_feedback(
            text=text,
            level=req.level,
            goal_level=req.goal_level,
            estimated_level=estimated_level,
        )

    return MonologueAnalyzeResponse(
        feedback=feedback,
        estimated_level=estimated_level,
        goal_level=req.goal_level,
        normalized_text=normalized_text,
        detected_issues=len(heuristic_issues),
    )


@app.post("/exam/practice", response_model=ExamPracticeResponse)
def exam_practice(req: ExamPracticeRequest) -> ExamPracticeResponse:
    level = _safe_level(req.level)
    exam_name: ExamName = "goethe"
    topic = pick_exam_topic(section=req.section, topic=req.topic)
    title = f"{EXAM_DISPLAY_NAMES[exam_name]} · {EXAM_SECTION_NAMES[req.section]} · {level}"
    official_basis = build_official_basis(exam=exam_name, section=req.section, level=level)
    content = build_exam_practice_content(
        level=level,
        exam=exam_name,
        section=req.section,
        topic=topic,
    )
    return ExamPracticeResponse(
        exam=exam_name,
        section=req.section,
        level=level,
        title=title,
        official_basis=official_basis,
        content=content,
    )


@app.post("/exam/mock/start", response_model=ExamMockStartResponse)
def exam_mock_start(req: ExamMockStartRequest) -> ExamMockStartResponse:
    level = _safe_level(req.level)
    exam_name: ExamName = "goethe"
    topic = pick_exam_topic(section=req.module, topic=req.topic)
    questions, instructions = build_question_set(
        level=level,
        module=req.module,
        topic=topic,
        count=req.question_count,
    )
    if not questions:
        raise HTTPException(status_code=400, detail="No se pudieron generar preguntas para este modulo.")

    mock_id = uuid4().hex
    estimated_minutes = max(6, len(questions) * (3 if req.module in {"sprechen", "schreiben"} else 1))
    with EXAM_MOCKS_LOCK:
        EXAM_MOCKS[mock_id] = {
            "exam": exam_name,
            "module": req.module,
            "level": level,
            "topic": topic,
            "questions": questions,
            "created_at": utc_now_iso(),
        }

    return ExamMockStartResponse(
        mock_id=mock_id,
        exam=exam_name,
        module=req.module,
        level=level,
        title=build_mock_meta_title(exam_name, req.module, level),
        instructions=instructions,
        estimated_minutes=estimated_minutes,
        questions=[to_public_question(question) for question in questions],
    )


@app.post("/exam/mock/submit", response_model=ExamMockSubmitResponse)
def exam_mock_submit(req: ExamMockSubmitRequest) -> ExamMockSubmitResponse:
    with EXAM_MOCKS_LOCK:
        mock_payload = EXAM_MOCKS.get(req.mock_id)
    if not mock_payload:
        raise HTTPException(status_code=404, detail="Simulacro no encontrado o expirado.")

    questions: list[GeneratedQuestionDict] = mock_payload.get("questions", [])
    if not questions:
        raise HTTPException(status_code=400, detail="El simulacro no contiene preguntas.")

    results: list[QuestionEvaluation] = []
    total_score = 0
    max_score = 0

    for question in questions:
        qid = question["id"]
        user_answer = str(req.answers.get(qid, "")).strip()
        q_max = int(question.get("max_points", 1))
        max_score += q_max

        if question["type"] == "open":
            score, is_correct, feedback, corrected = evaluate_open_answer(
                question,
                user_answer,
                level=mock_payload["level"],
                module=mock_payload["module"],
            )
            expected = "Respuesta abierta (sin clave unica)."
            if corrected:
                feedback = f"{feedback} Correccion sugerida: {corrected}"
        else:
            score, is_correct, feedback = evaluate_objective_answer(question, user_answer)
            expected = str(question.get("answer", ""))

        total_score += score
        results.append(
            QuestionEvaluation(
                question_id=qid,
                prompt=question["prompt"],
                user_answer=user_answer,
                correct_answer=expected,
                score=score,
                max_score=q_max,
                is_correct=is_correct,
                feedback=feedback,
            )
        )

    percent = round((total_score / max_score) * 100, 1) if max_score else 0.0
    return ExamMockSubmitResponse(
        mock_id=req.mock_id,
        exam=mock_payload["exam"],
        module=mock_payload["module"],
        level=mock_payload["level"],
        score=total_score,
        max_score=max_score,
        percent=percent,
        passed=percent >= 60.0,
        summary=summarize_score(total_score, max_score),
        results=results,
    )


@app.post("/exercise/set", response_model=ExerciseSetResponse)
def exercise_set(req: ExerciseSetRequest) -> ExerciseSetResponse:
    level = _safe_level(req.level)
    topic = pick_exam_topic(section=req.focus, topic=req.topic)
    questions, instructions = build_question_set(
        level=level,
        module=req.focus,
        topic=topic,
        count=req.count,
    )
    if not questions:
        raise HTTPException(status_code=400, detail="No se pudieron generar ejercicios para este foco.")

    set_id = uuid4().hex
    with EXERCISE_SETS_LOCK:
        EXERCISE_SETS[set_id] = {
            "level": level,
            "focus": req.focus,
            "topic": topic,
            "questions": questions,
            "created_at": utc_now_iso(),
        }

    return ExerciseSetResponse(
        set_id=set_id,
        level=level,
        focus=req.focus,
        title=f"Ejercicios de {EXAM_SECTION_NAMES[req.focus]} · {level}",
        instructions=instructions,
        questions=[to_public_question(question) for question in questions],
    )


@app.post("/exercise/submit", response_model=ExerciseSubmitResponse)
def exercise_submit(req: ExerciseSubmitRequest) -> ExerciseSubmitResponse:
    with EXERCISE_SETS_LOCK:
        set_payload = EXERCISE_SETS.get(req.set_id)
    if not set_payload:
        raise HTTPException(status_code=404, detail="Set de ejercicios no encontrado.")

    questions: list[GeneratedQuestionDict] = set_payload.get("questions", [])
    if not questions:
        raise HTTPException(status_code=400, detail="El set no contiene ejercicios.")

    results: list[QuestionEvaluation] = []
    total_score = 0
    max_score = 0

    for question in questions:
        qid = question["id"]
        user_answer = str(req.answers.get(qid, "")).strip()
        q_max = int(question.get("max_points", 1))
        max_score += q_max

        if question["type"] == "open":
            score, is_correct, feedback, corrected = evaluate_open_answer(
                question,
                user_answer,
                level=set_payload["level"],
                module=set_payload["focus"],
            )
            expected = "Respuesta abierta (sin clave unica)."
            if corrected:
                feedback = f"{feedback} Correccion sugerida: {corrected}"
        else:
            score, is_correct, feedback = evaluate_objective_answer(question, user_answer)
            expected = str(question.get("answer", ""))

        total_score += score
        results.append(
            QuestionEvaluation(
                question_id=qid,
                prompt=question["prompt"],
                user_answer=user_answer,
                correct_answer=expected,
                score=score,
                max_score=q_max,
                is_correct=is_correct,
                feedback=feedback,
            )
        )

    percent = round((total_score / max_score) * 100, 1) if max_score else 0.0
    return ExerciseSubmitResponse(
        set_id=req.set_id,
        level=set_payload["level"],
        focus=set_payload["focus"],
        score=total_score,
        max_score=max_score,
        percent=percent,
        summary=summarize_score(total_score, max_score),
        results=results,
    )


@app.post("/flashcards/generate", response_model=FlashcardsGenerateResponse)
def flashcards_generate(req: FlashcardsGenerateRequest) -> FlashcardsGenerateResponse:
    level = _safe_level(req.level)
    cards_raw = build_flashcards(level=level, topic=req.topic, count=req.count)
    if not cards_raw:
        raise HTTPException(status_code=400, detail="No se pudieron generar flashcards para ese tema.")

    set_id = uuid4().hex
    with FLASHCARD_SETS_LOCK:
        FLASHCARD_SETS[set_id] = {
            "level": level,
            "topic": req.topic,
            "cards": cards_raw,
            "created_at": utc_now_iso(),
        }

    cards = [
        FlashcardItem(
            id=card["id"],
            front=card["front"],
            back=card["back"],
            example=card["example"],
        )
        for card in cards_raw
    ]
    return FlashcardsGenerateResponse(
        set_id=set_id,
        level=level,
        topic=req.topic,
        cards=cards,
        study_tip=(
            "Haz ciclos cortos: mira el frente, responde en voz alta, comprueba y repite la carta en 24h."
        ),
    )


@app.post("/flashcards/check", response_model=FlashcardCheckResponse)
def flashcards_check(req: FlashcardCheckRequest) -> FlashcardCheckResponse:
    with FLASHCARD_SETS_LOCK:
        payload = FLASHCARD_SETS.get(req.set_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Set de flashcards no encontrado.")

    cards = payload.get("cards", [])
    card = next((item for item in cards if item.get("id") == req.card_id), None)
    if not card:
        raise HTTPException(status_code=404, detail="Flashcard no encontrada.")

    is_correct, feedback = evaluate_flashcard_answer(
        expected=str(card.get("back", "")),
        synonyms=[str(item) for item in card.get("synonyms", [])],
        user_answer=req.answer,
    )
    return FlashcardCheckResponse(
        set_id=req.set_id,
        card_id=req.card_id,
        is_correct=is_correct,
        expected=str(card.get("back", "")),
        feedback=feedback,
    )


@app.get("/transcript/{conversation_id}", response_model=TranscriptResponse)
def transcript(conversation_id: str) -> TranscriptResponse:
    session = get_session_snapshot(conversation_id)
    if not session:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    entries = build_transcript_response_entries(get_active_transcript(session))
    coherence = _copy_session_coherence(session.get("coherence"))
    return TranscriptResponse(
        conversation_id=conversation_id,
        level=session["level"],
        started_at=session["started_at"],
        persona_key=coherence.get("persona_key"),
        transcript=entries,
    )


@app.get("/api/chat/transcript/{conversation_id}", response_model=TranscriptResponse)
def api_chat_transcript(conversation_id: str) -> TranscriptResponse:
    return transcript(conversation_id)


@app.get("/api/chat/transcript/{conversation_id}/message/{entry_id}/versions", response_model=MessageVersionsResponse)
def api_chat_message_versions(conversation_id: str, entry_id: str) -> MessageVersionsResponse:
    session = get_session_snapshot(conversation_id)
    if not session:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    target_entry = find_transcript_entry(session, entry_id, role="user")
    if not target_entry:
        raise HTTPException(status_code=404, detail="User message not found.")

    version_group_id = _clean_optional_str(target_entry.get("version_group_id"))
    if not version_group_id:
        raise HTTPException(status_code=500, detail="User message is missing version metadata.")

    active_entry = get_active_user_entry_for_version_group(session, version_group_id)
    return MessageVersionsResponse(
        conversation_id=conversation_id,
        entry_id=entry_id,
        active_entry_id=str(active_entry.get("id")) if active_entry and active_entry.get("id") else None,
        versions=build_transcript_response_entries(list_user_versions(session, version_group_id)),
    )


@app.post("/api/chat/message/edit", response_model=TranscriptMutationResponse)
def api_chat_edit_message(req: ChatEditMessageRequest) -> TranscriptMutationResponse:
    return mutate_user_message_version(
        conversation_id=req.conversation_id,
        entry_id=req.entry_id,
        replacement_text=req.text,
        source="edited",
    )


@app.post("/api/chat/message/restore", response_model=TranscriptMutationResponse)
def api_chat_restore_message(req: ChatRestoreMessageRequest) -> TranscriptMutationResponse:
    return mutate_user_message_version(
        conversation_id=req.conversation_id,
        entry_id=req.entry_id,
        replacement_text="",
        source="restored",
        restore_from_entry_id=req.restore_from_entry_id,
    )


@app.post("/finish", response_model=FinishResponse)
def finish(req: FinishRequest) -> FinishResponse:
    session = get_session_snapshot(req.conversation_id)
    if not session:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    active_transcript = get_active_transcript(session)
    if not active_transcript:
        raise HTTPException(status_code=400, detail="Conversation transcript is empty.")
    if not transcript_has_completed_assistant_turn(active_transcript):
        raise HTTPException(
            status_code=400,
            detail="Conversation has no completed assistant turn yet.",
        )

    provider = resolve_provider()
    if provider == "rulebased" and should_block_rulebased_mode():
        raise HTTPException(status_code=503, detail=rulebased_block_detail())
    try:
        if provider == "ollama":
            try:
                feedback = finish_with_ollama(level=session["level"], transcript=active_transcript)
            except RuntimeError:
                feedback = rulebased_feedback(active_transcript, session["level"])
        else:
            feedback = rulebased_feedback(active_transcript, session["level"])
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not feedback:
        feedback = (
            "No se pudo generar un analisis automatico completo. "
            "Intentalo de nuevo en unos segundos."
        )

    entries = build_transcript_response_entries(active_transcript)
    return FinishResponse(
        conversation_id=req.conversation_id,
        level=session["level"],
        transcript=entries,
        feedback=feedback,
    )


@app.post("/api/chat/finish", response_model=FinishResponse)
def api_chat_finish(req: FinishRequest) -> FinishResponse:
    return finish(req)

