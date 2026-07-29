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

## Specialist bots

Create domain-specific sub-bots that share memory but maintain isolated chat.

`coding-bot` is bootstrapped automatically on startup with four active coding skills. See [docs/NOTES.md](../docs/NOTES.md) for full details.

- `POST /specialists` — register a new specialist (slug, name, sector, system_prompt)
- `GET /specialists` — list all specialists
- `GET /specialists/{slug}` — get specialist details
- `PATCH /specialists/{slug}` — update name, prompt, or enable/disable
- `DELETE /specialists/{slug}` — remove a specialist
- `POST /specialists/{slug}/chat` — chat with a specific specialist
- `GET /specialists/{slug}/history` — get specialist's chat history

Example: create a trading bot:

```json
POST /specialists
{
  "slug": "trading-bot",
  "name": "Trading Bot",
  "sector": "trading",
  "system_prompt": "You are an expert stock trader. Provide analysis using local data only."
}
```

Then chat with it:

```json
POST /specialists/trading-bot/chat
{ "message": "Should I hold AAPL?" }
```

## Learnable skills

Define reusable skills and teach them to specialists (or the main bot):

- `POST /skills` — define a new skill (slug, category, instructions, parameters_schema)
- `GET /skills` — list all skill definitions
- `GET /skills/{slug}` — get a skill
- `POST /specialists/{slug}/skills` — teach a skill to a specialist (with custom parameters)
- `GET /specialists/{slug}/skills` — list skills a specialist has learned
- `POST /skills/assignments/{id}/activate` — mark a learned skill as active
- `PATCH /skills/assignments/{id}` — update parameters or status
- `POST /skills/learn` — teach a skill to the main bot globally

Example: teach a trading bot to analyze stocks:

```json
POST /skills
{
  "slug": "stock-analysis",
  "name": "Stock Analysis",
  "category": "trading",
  "instructions": "Analyze using P/E ratio, moving averages, and volume trends.",
  "parameters_schema": {"ticker_symbols": {"type": "list"}, "depth": {"type": "string"}}
}

POST /specialists/trading-bot/skills
{ "skill_slug": "stock-analysis", "parameters": {"ticker_symbols": ["AAPL", "GOOG"]} }

POST /skills/assignments/1/activate
```

Once active, the skill's instructions and parameters are injected into every chat response.

## 24x7 runtime

- `GET /runtime/status` — uptime, heartbeat count, last heartbeat
- `POST /runtime/heartbeat` — manually trigger a heartbeat
- `GET /runtime/heartbeats` — recent heartbeat history
- Background heartbeat runs automatically every 60 seconds

## Voice assistant

- UI: http://127.0.0.1:8000/ui/voice.html (browser mic works without extra packages)
- `GET /voice/status` · `POST /voice/start` · `POST /voice/stop` · `PATCH /voice/config`
- `POST /voice/command` — process a transcript (`shared=true` required)
- Optional wake-word deps: `pip install -e ".[voice]"` then `PROJECT_WE_VOICE_ENABLED=true`

Env vars:

- `PROJECT_WE_VOICE_ENABLED` (`true`/`false`)
- `PROJECT_WE_VOICE_WAKE_WORD` (default: `hey jarvis`)
- `PROJECT_WE_VOICE_WAKE_SENSITIVITY` (default: `0.5`)
- `PROJECT_WE_VOICE_STT_MODEL` (default: `base`)
- `PROJECT_WE_VOICE_TTS_VOICE` (default: `en_US-amy-medium`)
- `PROJECT_WE_VOICE_SILENCE_THRESHOLD` (default: `1.5`)

## Test

```bash
pytest
```

## Lint

```bash
ruff check .
```
