# AI German Tutor System

Public, sanitized portfolio repository for a local-first German learning assistant built with FastAPI, local speech/transcription tooling, tutor personas, and progress persistence.

## What is included

- FastAPI backend and frontend assets
- learning services for tutoring, placement, progress, exam practice, and TTS integration
- test suite for platform features, schema behavior, tutor TTS, and chat resilience
- `.env.example` with placeholder configuration for local setup

## What is intentionally excluded

- private `.env` files and credentials
- SQLite runtime databases
- personal learning history and private conversations
- recorded audio, local model weights, Ollama runtime data, and Piper voice files
- local HTTPS certificates, tunnel state, caches, and logs

## Local setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

## Run tests

```powershell
pytest
```

## Run locally

```powershell
python main.py
```

The app is designed for local-first use. Optional speech, tunnel, and TTS features require installing the external tools referenced in `.env.example`, `run_public_tunnel.py`, and the launcher scripts.
