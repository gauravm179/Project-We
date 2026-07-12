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

## Test

```bash
pytest
```

## Lint

```bash
ruff check .
```
