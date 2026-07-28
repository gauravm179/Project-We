# Project We Architecture (v0.3)

## Service boundaries

- **API layer** (`backend/app/api`): request/response contracts and HTTP routes
- **Brain layer** (`backend/app/brain`): provider-agnostic chat orchestration
- **Memory layer** (`backend/app/memory`): extraction and persistence of facts/preferences/tasks
- **Policy layer** (`backend/app/policy`): strict local mode and internet permission requests
- **Input layer** (`backend/app/inputs`): screen/voice ingestion with explicit sharing guard
- **Control layer** (`backend/app/control`): consented assistive screen-control sessions and action queue
- **Safety layer** (`backend/app/safety`): SOS emergency stop state and app-wide lock enforcement
- **Specialists layer** (`backend/app/specialists`): domain-specific sub-bots with isolated chat history
- **Data layer** (`backend/app/db`): SQLite persistence for conversation records
- **Core layer** (`backend/app/core`): config and logging

## Data flow

1. Client sends `POST /chat` with a user message.
2. API route calls `BrainService`.
3. `BrainService` selects provider (`echo` or `ollama`).
4. User message is persisted and passed through memory extraction.
5. Policy checks if request likely needs live internet data.
6. If needed and mode is `ask`, a permission request is created and returned.
7. If permitted or local-only, assistant response is generated and persisted.
8. API returns structured chat response.

## Shared input policy

- Screen and voice context ingestion are disabled by default unless payload includes `shared=true`.
- Accepted screen/voice content is persisted and processed through memory extraction.
- This keeps screen/audio capture explicit and user-controlled.

## Assistive control policy

- Control requires explicit session consent (`shared=true`).
- Action execution is two-step: queue -> approve/reject -> execute.
- Write actions are blocked when session `allow_write=false`.
- Screen context can be interpreted locally for email drafting and form assistance.

## SOS shutdown policy

- SOS is a permanent capability that cannot be removed via API.
- Trigger endpoint: `POST /safety/sos/trigger`.
- While active, all non-safety endpoints are blocked by middleware (`423 Locked`).
- Safety status remains queryable through `GET /safety/status`.

## Local-first policy

- Database is local (`data/project_we.db` by default).
- No network calls unless provider is explicitly set to `ollama`.
- Provider can be replaced without changing memory storage format.
- Internet-required queries can be blocked or gated via `PROJECT_WE_INTERNET_MODE`.

## Specialist bots

- Each specialist is a named sub-bot with a unique `slug`, `sector`, and custom `system_prompt`.
- Specialists can be created, updated, enabled/disabled, and deleted via REST.
- Chat flows through the same AI provider as the main bot, but the specialist's `system_prompt` is injected into the model context.
- Each specialist maintains its own isolated chat history (`specialist_messages` table).
- Specialists share the global memory store (facts, preferences, tasks).
- Duplicate slugs are rejected (`409 Conflict`).

```
Main Bot (Project We)
 ├── trading-bot      (sector: trading)
 ├── troubleshoot-bot  (sector: troubleshooting)
 ├── health-bot        (sector: health)
 ├── coding-bot        (sector: coding, bootstrapped with active coding skills)
 └── ... (user-defined)
```

## Learnable skills

Skills are parameterized capabilities that bots learn on demand.

- **Skill definition**: A reusable template with `slug`, `category`, `instructions`, and a `parameters_schema`.
- **Learning flow**: `learning` → `active` → (optionally `paused`). Only `active` skills are injected into the AI prompt.
- **Parameter-driven**: Each skill assignment carries its own parameter values (e.g. ticker symbols for a trading skill, log patterns for a debug skill).
- **Prompt injection**: Active skills are appended to the specialist's system prompt as `--- LEARNED SKILLS ---` blocks with instructions and parameters.
- **Scope**: Skills can be assigned to a specific specialist or to the main bot globally.

```
Skill "stock-analysis" (category: trading)
  └── Assigned to trading-bot with parameters: {ticker_symbols: [AAPL, GOOG]}
  └── Status: active → injected into every chat response

Skill "log-diagnosis" (category: troubleshooting)
  └── Assigned to troubleshoot-bot with parameters: {log_source: splunk}
  └── Status: learning → NOT injected yet
```

## 24x7 runtime

- **Heartbeat loop**: Background asyncio task records heartbeats every 60 seconds to the `heartbeats` table.
- **Uptime tracking**: Process start time is recorded; `GET /runtime/status` returns current uptime, heartbeat count, and last heartbeat timestamp.
- **Manual heartbeats**: `POST /runtime/heartbeat` for on-demand health checks.
- **Resilience**: The heartbeat loop handles exceptions gracefully so a single DB failure doesn't crash the app.

## Next milestones

- Document ingestion + semantic retrieval
- Voice I/O module
- Desktop client (Tauri + React)
- Specialist auto-routing (main chat routes to relevant specialist)
- Skill auto-suggestion from conversation context
