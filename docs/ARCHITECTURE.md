# Project We Architecture (v0.2)

## Service boundaries

- **API layer** (`backend/app/api`): request/response contracts and HTTP routes
- **Brain layer** (`backend/app/brain`): provider-agnostic chat orchestration
- **Memory layer** (`backend/app/memory`): extraction and persistence of facts/preferences/tasks
- **Policy layer** (`backend/app/policy`): strict local mode and internet permission requests
- **Input layer** (`backend/app/inputs`): screen/voice ingestion with explicit sharing guard
- **Control layer** (`backend/app/control`): consented assistive screen-control sessions and action queue
- **Safety layer** (`backend/app/safety`): SOS emergency stop state and app-wide lock enforcement
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

## Next milestones

- Document ingestion + semantic retrieval
- Voice I/O module
- Desktop client (Tauri + React)
