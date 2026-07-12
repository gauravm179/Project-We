# Project We Backend

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

## Memory in v0.2

- User messages are scanned for structured memory candidates.
- Supported memory types: `fact`, `preference`, `task`.
- Read memories via:
  - `GET /memory`
  - `GET /memory/summary`

## Strict local + live input

- Internet-gated chat in strict local mode:
  - internet mode `ask` creates permission requests for likely live-data queries
  - endpoints:
    - `GET /permissions`
    - `POST /permissions`
    - `POST /permissions/{id}/decision`
- Live inputs (only with explicit share):
  - `POST /inputs/screen` requires `shared=true`
  - `POST /inputs/voice` requires `shared=true`

## Screen control (consent-based)

- `POST /control/sessions` opens a scoped control session (`shared=true` required).
- `POST /control/sessions/{id}/assist` uses shared screen context for:
  - `email_draft`
  - `form_fill`
- `POST /control/actions` queues proposed actions.
- `POST /control/actions/{id}/decision` approves/rejects queued actions.
- `POST /control/actions/{id}/execute` executes only approved actions.

## SOS emergency stop (non-removable)

- `POST /safety/sos/trigger` enables emergency shutdown immediately.
- `GET /safety/status` is still available while shutdown is active.
- All non-safety endpoints return `423 Locked` once SOS is active.
- No endpoint exists to remove or disable SOS capability.

## Test

```bash
pytest
```

## Lint

```bash
ruff check .
```
