# AGENTS.md

## Cursor Cloud specific instructions

### Product overview

Project We is a local-first personal assistant backend (v0.2). The repo contains a single **Python FastAPI** service under `backend/` — no frontend or Docker Compose yet.

### Services

| Service | Required? | Notes |
|---------|-----------|-------|
| FastAPI backend (`uvicorn`) | **Yes** | Only service needed for E2E |
| SQLite | Implicit | Auto-created at `data/project_we.db` on startup |
| Ollama | Optional | Set `PROJECT_WE_PROVIDER=ollama` for real LLM; default is `echo` |

### Common commands

All commands run from `backend/` with the virtualenv activated (`.venv/bin/...`):

| Task | Command |
|------|---------|
| Install deps | `pip install -e ".[dev]"` |
| Dev server | `uvicorn app.main:app --reload` |
| Tests | `pytest` |
| Lint | `ruff check .` |

See `README.md` and `backend/README.md` for full setup and env-var docs.

### Non-obvious caveats

- **Python venv**: Ubuntu images may lack `python3-venv`. Install `python3.12-venv` (or matching version) before `python3 -m venv .venv`.
- **Working directory**: Run `uvicorn` from `backend/` so `app.main:app` resolves correctly.
- **Default provider**: Echo provider needs no external services; Ollama requires a running Ollama daemon and model pull.
- **Ruff lint**: `ruff check .` may report pre-existing B008 (`Depends` in defaults) and style warnings; tests still pass.
- **Data directory**: SQLite and local data live in repo-root `data/`; created automatically on first server start.
