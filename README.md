# Project We

Project We is a local-first personal assistant foundation designed to run on macOS and Windows.

## Current milestone

This repository currently contains **v0.2 backend foundation**:

- FastAPI backend with health and chat endpoints
- SQLite persistence for conversation history
- Structured memory extraction (`facts`, `preferences`, `tasks`)
- Memory listing and summary endpoints
- Strict local policy defaults with internet permission gating
- Live screen and voice ingestion endpoints (only when explicitly shared)
- AI provider abstraction
- Optional Ollama provider integration
- Unit tests with pytest

## Design principles

- Local-first: user data stays on your machine
- Cross-platform: same codebase for macOS and Windows
- Transparent: explicit settings and modular services
- Replaceable: model providers can be swapped without breaking memory/data

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — service layers and data flow
- [Agent notes](docs/NOTES.md) — system config, bot hierarchy, coding-bot training, dev commands

## Quick start

1. Clone this repository.
2. Go to backend:

   ```bash
   cd backend
   ```

3. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   # macOS/Linux:
   source .venv/bin/activate
   # Windows (PowerShell):
   # .venv\Scripts\Activate.ps1

   pip install -e ".[dev]"
   ```

4. Run the API:

   ```bash
   uvicorn app.main:app --reload
   ```

5. Open docs:

   - [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
   - [http://127.0.0.1:8000/ui/](http://127.0.0.1:8000/ui/) — local browser chat for `coding-bot`

## API endpoints

- `GET /` - service metadata and status
- `POST /chat` - send message and get assistant response
- `GET /chat/history` - read persisted chat history
- `GET /memory` - read extracted structured memory
- `GET /memory/summary` - grouped memory counts by type
- `GET /permissions` - list permission requests
- `POST /permissions` - create manual permission request
- `POST /permissions/{id}/decision` - approve/reject permission request
- `POST /inputs/screen` - ingest screen context when `shared=true`
- `POST /inputs/voice` - ingest voice transcript when `shared=true`
- `POST /control/sessions` - open a consented control session
- `POST /control/sessions/{id}/assist` - draft email/form guidance from shared screen context
- `POST /control/actions` - queue a control action (pending approval)
- `POST /control/actions/{id}/decision` - approve/reject queued action
- `POST /control/actions/{id}/execute` - execute approved action record
- `GET /safety/status` - read SOS emergency-stop state
- `POST /safety/sos/trigger` - trigger immediate app shutdown (red button flow)

## Provider configuration

By default, the backend uses a local echo provider.

To use Ollama:

```bash
export PROJECT_WE_PROVIDER=ollama
export PROJECT_WE_OLLAMA_MODEL=qwen2.5:7b
export PROJECT_WE_OLLAMA_BASE_URL=http://127.0.0.1:11434
```

Windows PowerShell:

```powershell
$env:PROJECT_WE_PROVIDER="ollama"
$env:PROJECT_WE_OLLAMA_MODEL="qwen2.5:7b"
$env:PROJECT_WE_OLLAMA_BASE_URL="http://127.0.0.1:11434"
```

## Strict local policy defaults

Project We now runs in strict local mode by default and asks before internet-required assistance:

```bash
export PROJECT_WE_STRICT_LOCAL_MODE=true
export PROJECT_WE_INTERNET_MODE=ask
```

Valid internet modes:

- `ask` (default): create a permission request when internet likely needed
- `never`: refuse internet-required requests
- `always`: allow normal response flow (internet tools still need to be implemented)

## Assistive control mode

Project We supports a safe, consent-based control workflow:

- control session only starts with `shared=true`
- write actions can be disabled per session (`allow_write=false`)
- all actions are queued and require explicit approval before execution
- screen context can be used to draft emails and suggest form field values

## Red SOS emergency stop

- A permanent red SOS button in UI should call `POST /safety/sos/trigger`.
- Once triggered, non-safety endpoints are locked with `423 Locked`.
- There is intentionally no API to disable/remove SOS behavior.
