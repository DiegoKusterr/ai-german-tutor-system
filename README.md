# AI German Tutor System

## Overview

This repository contains a local-first German learning system built around a FastAPI backend, a browser frontend, SQLite persistence, and optional local LLM and speech tooling. It is designed for conversational practice, correction workflows, exam preparation, progress tracking, and tutor-style feedback without depending on a hosted SaaS stack.

The public repository keeps the application code, prompts, tests, frontend assets, and `.env.example` placeholders. It excludes private study history, runtime databases, local model weights, recorded audio, voice files, and local certificates.

## Problem and Objective

Language-learning tools often separate tutoring, correction, speaking practice, and progress tracking into different products. This project aims to keep those flows in one local-first system while preserving control over study data and runtime dependencies.

The main objective is to support German practice across conversation, guided feedback, and exam-style preparation from a single application.

## Architecture

```text
FastAPI application
  - tutoring endpoints
  - exam and practice flows
  - transcription and TTS endpoints
        |
        v
learning_app/
  - services
  - prompts
  - schemas
  - SQLite data layer
        |
        v
Static frontend
  - chat
  - exam prep
  - progress views
  - tutor runtime
```

The system is local-first by default: the backend, database, optional model runtime, and optional speech stack can all run on the same machine.

## Conversation and Feedback Flow

The public codebase includes:

- tutor personas for different interaction styles
- conversational practice routes
- correction and feedback generation
- placement and roadmap flows
- exam-practice and mock-exam generation
- frontend logic that keeps tutor identity and playback behavior consistent across a session

This is more than a single chat endpoint: it is a study workflow with tutoring, review, and exam-oriented features.

## Speech and Audio Pipeline

Speech support is optional and remains local-first.

- local transcription can run through Whisper-compatible tooling when available
- tutor audio can use local Piper TTS, with browser fallback behavior exposed in the app
- mock exam audio helpers are included in the repository
- required model files and voice files are intentionally not committed

The public repo documents the configuration surface in `.env.example` without shipping the local runtime assets themselves.

## Memory and Progress Tracking

Progress is stored locally in SQLite.

The public code covers:

- session persistence
- spaced-review logic
- placement history
- progress-overview calculations
- roadmap generation
- exam-history and mistake-tracking support

This keeps the learning state tied to the local application instead of an external hosted profile.

## Privacy and Local-First Design

Privacy is part of the architecture, not an afterthought.

- no private `.env` files are committed
- local SQLite databases are excluded from version control
- personal conversations, recorded audio, and runtime model assets are excluded
- optional tunnel and HTTPS helpers exist for local workflows, but the application does not require a public deployment

There is no public hosted demo in this repository; the project is intended to run locally.

## Tech Stack

- Python
- FastAPI
- SQLite
- Ollama
- Faster Whisper
- optional Piper TTS
- HTML, CSS, and JavaScript
- pytest

## Testing

The repository includes automated coverage for:

- chat coherence and resilience
- schema behavior
- platform and progress features
- local HTTPS helpers
- tutor TTS behavior and fallbacks

Run the suite with:

```powershell
pytest
```

## Run Locally

1. Create and activate a virtual environment.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

2. Configure the local tools you want to enable in `.env`.

- set the local Ollama endpoint and model
- enable transcription if your local Whisper-compatible setup is available
- add Piper voice paths only if you want local tutor TTS

3. Run tests if you want to validate the public setup first.

```powershell
pytest
```

4. Start the application.

```powershell
python main.py
```

## Limitations

- Full speech and audio behavior depends on local runtime tools and model/voice files that are not bundled with the repository.
- There is no public hosted deployment in this project; it is designed for local use.
- The public repo excludes personal learning history, local databases, certificates, and runtime assets by design.
