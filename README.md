# AI German Tutor System

A personal engineering portfolio project for German conversation practice and structured study. It combines a Python/FastAPI backend, a browser interface, local Ollama inference, and persistent learning workflows. The aim is to connect practice, feedback, review and progress tracking while keeping the application's learning data on the user's computer.

This is a **desktop-first, locally hosted, single-user prototype**, not a production service or a validated language assessment product. Windows desktop browser text conversations and browser-based German voice playback have been manually tested. Running the app requires local Python, Ollama and dependency setup; this repository is not a publicly hosted interactive demo.

## Implemented features

| Area | Implementation |
| --- | --- |
| Conversation | German tutor personas, blocking and NDJSON streaming APIs, contextual prompts, history, message editing and version restoration |
| Structured study | Grammar exercises and reference material, writing prompts, text-based speaking simulations, vocabulary and flashcards |
| Exam preparation | Exam-style practice and mock generation, placement, goal selection and study roadmaps; generated material is not an official exam |
| Review and progress | SM-2 review scheduling, mistake tracking, activity streaks and target-level readiness indicators |
| Analysis and controls | Strategy comparison labels, manual-review records, analytics and CSV exports with formula-like text neutralized |
| Optional audio | Faster Whisper transcription, Piper tutor speech, browser speech fallbacks and Windows mock-exam audio helpers |

The backend feature set is broader than the currently visible browser controls. Some frontend elements are compatibility controls rather than visible navigation. The presence of an API or frontend handler does not establish that its complete browser workflow works. See the verification scope below.

## Architecture and stack

```text
Browser: HTML / CSS / JavaScript, served by FastAPI
    |
    | HTTP JSON + NDJSON streaming
    v
main.py: app, chat orchestration, streaming, transcription
    |-- Ollama HTTP API on 127.0.0.1:11434
    |-- JSON state: chat sessions and conversational learner profile
    |-- optional local Whisper / Piper adapters
    |
learning_app/router.py -> services -> SQLite
    structured practice, goals, exam history, review and analytics
```

There is no separate frontend build step, hosted LLM requirement or database server. Python's standard library supplies SQLite; Ollama is a separate local executable, not a Python package.

| Path | Responsibility |
| --- | --- |
| `main.py` | FastAPI application and conversational workflows |
| `learning_app/router.py`, `learning_app/schemas.py` | Structured-learning API and Pydantic contracts |
| `learning_app/services/` | Learning, progress, review, assessment, export and optional audio logic |
| `learning_app/db.py`, `learning_app/config.py` | SQLite schema/connections and configuration |
| `static/` | Browser interface and assets |
| `tests/` | Unit, in-process API and synthetic persistence regression tests |
| `.env.example` | Example configuration without credentials or learner data |

## Local setup — Windows and Python 3.11

Run these commands from the repository root in PowerShell. Python 3.11 is the audited interpreter family; other versions have not been established as compatible. Install Python and Ollama separately if they are not already available. Package installation needs an intentional network connection or an existing package cache; normal local chat does not require a hosted AI API.

### 1. Prepare the Python environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Activation is optional: the commands use the virtual environment's interpreter directly and require no PowerShell execution-policy changes. An existing `.env` is preserved. Review it manually rather than replacing personal settings. Explicit process environment variables take precedence over `.env` values.

`requirements.txt` contains the core application, automated-test dependencies and local HTTPS helper dependency. Optional speech packages are documented separately below. `httpx` is required by FastAPI's `TestClient`; `pytest` alone is insufficient. Pydantic 2 is required because the implementation uses its `model_dump`/`model_validate` APIs. Windows also needs `tzdata` for named IANA time zones.

### 2. Prepare an existing local Ollama model

Use an already installed model. In a separate PowerShell terminal, start Ollama only if no Ollama instance is already running:

```powershell
$env:OLLAMA_HOST = '127.0.0.1:11434'
ollama serve
```

In the application terminal, check the local installation:

```powershell
$env:OLLAMA_HOST = '127.0.0.1:11434'
ollama list
ollama show llama3.2:1b
```

If the model is absent, choose another already installed model or arrange a model download separately. The ordinary application launcher does not install Ollama or download a missing model. Do not start a second Ollama daemon over an existing instance.

### 3. Review `.env`

The example provides the low-resource profile used in the earlier local performance investigation:

```dotenv
CHAT_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2:1b
OLLAMA_NUM_CTX=1280
OLLAMA_NUM_THREAD=4
OLLAMA_KEEP_ALIVE=30m
OLLAMA_SPEED_PRESET=quality
OLLAMA_ENABLE_STARTUP_WARMUP=1
OLLAMA_STARTUP_WARMUP_DELAY_SEC=0
OLLAMA_CHAT_MAX_TOKENS=72
```

Warm-up and conversation requests share model/context/thread/keep-alive settings; warm-up generates only one token. Runtime settings no longer switch based on turn count. `OLLAMA_CHAT_MAX_TOKENS` is a generation budget, not a word count. Native length-limit termination is exposed in chat/stream metadata and the streaming UI warns when it occurs. Partial text is retained; continuation is a separate learner request.

For the optional larger model, change only the model selection initially:

```dotenv
OLLAMA_MODEL=llama3.2:3b
```

Keep the context/thread settings explicit when comparing configurations. The 3B model remains available; the 1B model is not assumed to produce better answers. CPU, available RAM, context length, other running programs and model choice affect latency and quality. The combined revised application has not received another real-model benchmark. Existing defaults retain a 35-second chat backend timeout and a 45-second frontend request limit; slow requests can still fail.

### 4. Start one local application instance

Use the corrected Windows launcher:

```powershell
.\iniciar_chatbot.bat
```

Or run Uvicorn directly with the same local binding:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Then manually open `http://127.0.0.1:8000`. API documentation is at `http://127.0.0.1:8000/docs`. Stop the selected application process with Ctrl+C. `python main.py` does not start an ASGI server.

The Windows launcher uses an existing `.venv`, waits for backend readiness and does not open a browser by default. It does not install dependencies, start Ollama, install certificates or activate tunnels. If model readiness is not achieved, it reports an error instead of provisioning missing software.

## Persistence and configuration

| Store | Default location | Contents |
| --- | --- | --- |
| SQLite | `data/learning_app.db` | Structured-learning sessions, exercise/exam attempts, goals/settings, flashcards, reviews, recommendations and analytics |
| JSON | `data/state.json` | Conversational sessions/transcripts and the conversational learner profile |
| Runtime assets | Under `data/` by default | Optional audio caches, voice models and generated local HTTPS certificate files |

These stores coexist; conversation history is not all stored in SQLite. `APP_DATA_DIR` sets the application data directory; `APP_DB_PATH` independently sets the SQLite file. When changing data locations, set both explicitly before starting Python. Relative data paths are resolved from the working directory; run from the repository root. Some optional voice/certificate asset paths have their own configuration or remain relative to the project, so changing `APP_DATA_DIR` does not relocate every asset.

The app initializes its SQLite schema during normal startup and can update learning state during use. Back up both the SQLite store and JSON state before changing an existing installation. Data, private `.env` files, models and certificates are excluded by the supplied `.gitignore`; ignore rules do not remove files that were already tracked in another checkout.

## Verification scope and tests

Automated validation has used an existing Windows environment with Python **3.11.9**. Observed core package versions were FastAPI **0.128.0**, Pydantic **2.12.5**, Uvicorn **0.40.0**, python-dotenv **1.2.1**, python-multipart **0.0.21**, pytest **8.4.2**, HTTPX **0.28.1** and trustme **1.2.1**. These are observations, not a lockfile or a claim that every allowed future package version is compatible. A clean virtual-environment installation has not been executed as part of the audit.

| Evidence level | Scope |
| --- | --- |
| Verified by automated backend tests | Schemas, grammar/practice services, flashcards/review, target-level readiness, assessment input guards, completed-speaking-session rejection, CSV escaping and configuration loading |
| Verified in process with synthetic data | API behavior, local CORS handling, conversation commit/history, JSON save/load and SQLite interactions |
| Verified through mocks/source checks | Ollama request consistency, streaming events and truncation metadata, launcher defaults, public-mode safeguards, TTS adapters and browser voice selection/playback lifecycle |
| Verified by a short local API smoke test | Integrated application with existing `llama3.2:1b`: three fictional German conversation turns, genuine Ollama responses, incremental streaming, context recall and conversation persistence after restarting only FastAPI |
| Manually tested on Windows desktop | Browser text conversations and browser-based German voice playback |
| Requires further integration/manual testing | Complete browser navigation, microphone capture/transcription, optional audio providers and HTTPS; mobile layouts and audio workflows are not validated or optimized |
| Not established | Fresh installation, long-term reliability, production/public deployment, validated CEFR proficiency or exam pass prediction |

Earlier real-Ollama investigation informed the example configuration. The subsequent three-turn smoke test verifies only the short local API workflow above; it does not establish general language quality, fully functional voice interaction or long-term reliability. Mocked request tests do not prove actual model availability, speed, response quality or elimination of model reloads on another machine.

To avoid using personal learning stores, run tests in a **separate PowerShell terminal** with fresh temporary paths:

```powershell
$env:APP_DATA_DIR = Join-Path $env:TEMP ('german-tutor-tests-' + [guid]::NewGuid().ToString('N'))
$env:APP_DB_PATH = Join-Path $env:APP_DATA_DIR 'learning_app.db'
$env:OLLAMA_ENABLE_STARTUP_WARMUP = '0'
$env:EXAM_MOCK_LLM_ENABLED = '0'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
.\.venv\Scripts\python.exe -B -m pytest tests -q -p no:cacheprovider --basetemp (Join-Path $env:APP_DATA_DIR 'pytest')
```

Close that terminal afterwards so these process-only data overrides are not reused for normal study. Test artifacts stay in the temporary directory. Tests mock Ollama and audio generation; the command is not an operating-system network sandbox. Audit runs additionally used an external offline guard, which is not part of the application. Automated checks do not replace manual audio tests or establish fresh-install or long-term reliability.

The validated suites contain **242 Python tests** and **32 browser TTS regression tests**. The latter use Node.js's built-in test runner with mocked browser speech APIs and no npm packages:

```powershell
node --test tests/test_browser_tts.cjs
```

## Optional speech and audio

Text chat and structured-learning APIs can run without these optional packages or assets:

| Capability | Additional requirement | Status/limitations |
| --- | --- | --- |
| Server transcription | `faster-whisper` plus an available compatible model | Package/native import checked in the audit environment; microphone capture and real transcription not validated |
| Local tutor TTS | `piper-tts` plus a voice `.onnx` and matching `.onnx.json` | Piper was absent in the audit environment; adapter tests used mocks |
| Browser tutor playback | Browser speech synthesis and an available German system/browser voice | Manually tested on Windows; exact matches are retained, otherwise a German voice is selected. Requested gender is preferred when identifiable but is not guaranteed |
| Browser dictation | Compatible browser, microphone permission and a secure context where required | Microphone transcription is not validated end to end; recognition may use a vendor's external service |
| Mock-exam audio | Windows PowerShell/System.Speech and a suitable installed voice | Optional helper; disabled by `MOCK_AUDIO_PROVIDER=none` in the example; playback not validated |

Install an optional Python package only when deliberately enabling that feature, for example:

```powershell
.\.venv\Scripts\python.exe -m pip install faster-whisper
# Separately, if local tutor speech is wanted:
.\.venv\Scripts\python.exe -m pip install piper-tts
```

These commands install libraries, not speech assets. For offline transcription, set `LOCAL_TRANSCRIBE_MODEL` to an existing local Faster Whisper model directory and use `HF_HUB_OFFLINE=1`. A short model identifier such as the example's `base` may trigger a download on first transcription if it is not cached. Piper paths are documented in `.env.example`; model and voice files are not bundled. If audio is unavailable, use text input; browser fallback availability is not guaranteed.

Android/mobile layouts and audio workflows are not validated or optimized. The tested Android browser exposed no compatible German TTS voice. Accessing the app from another device over an insecure LAN HTTP connection may block microphone access, as observed during mobile testing. Browser playback can require a user tap on **Letzte Antwort**; missing voices or blocked playback are reported in the interface.

## Assessment and model limitations

Writing/speaking scores and CEFR readiness indicators are **uncalibrated heuristics**. Input-quality checks reduce inflated scores for empty, meaningless or repetitive submissions, and speaking evaluation aggregates learner turns, but these rules can still misjudge genuine responses. Text-based speaking assessment does not establish pronunciation quality or validated oral proficiency.

Readiness calculations use exam attempts at the selected target level; activity history and streaks remain cross-level. Compatibility API names such as `probability_percent` are retained, but the numbers are heuristic indicators, **not validated exam pass probabilities**. Missing or incomplete module data limits their interpretation. No predictive-accuracy or official CEFR certification claim is made.

LLM output can be inaccurate, grammatically wrong or poorly aligned with instructions. Generated practice is not endorsed by an examination provider. Native chat output is retained rather than silently rewritten to enforce sentence/word instructions. Token limits, timeouts and the available prompt context still constrain conversation continuity. Truncation metadata covers ordinary chat and streaming/commit paths; existing edit/regenerate and feedback schemas have not been extended with it.

## Privacy and network boundaries

The backend and Ollama default to loopback, and learning stores are local. No hosted model API or API key is required for the documented local setup. This does **not** mean that opening the interface guarantees zero external browser traffic: `static/index.html` references Google Fonts, and browser speech recognition may contact a vendor service. For strictly offline use, avoid browser dictation and use controlled browser network settings or local API clients; no browser isolation is supplied by this project.

Default CORS is an explicit list of local HTTP/HTTPS origins, without credentialed CORS. Custom cross-origin clients need deliberate `ALLOWED_ORIGINS` configuration. CORS is not authentication; this prototype has no production authentication/authorization boundary.

LAN binding requires an explicit launcher choice such as `--lan --host 0.0.0.0`. Local HTTPS is optional via `--https`; it generates certificate files and does not install a trust certificate. Public access uses the separate `run_public_tunnel.py` helper and requires **both** `--public` and `--demo-data-dir` pointing to a fresh, empty directory separate from personal learning data. It must start in a fresh process. An existing tunnel client is required; the helper does not install one. Use fictional demonstration content only. These optional network modes have not been validated end to end and should not be used to expose personal study data.

The older installation/microphone helper scripts are manual utilities, not prerequisites for local text use; they were not exercised in the audit. Review their effects before running them. There is no public hosted demo, and the project is not ready for an unprotected production deployment.
