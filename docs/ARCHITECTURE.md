# Project We Architecture (v0.2)

## Service boundaries

- **API layer** (`backend/app/api`): request/response contracts and HTTP routes
- **Brain layer** (`backend/app/brain`): provider-agnostic chat orchestration
- **Memory layer** (`backend/app/memory`): extraction and persistence of facts/preferences/tasks
- **Data layer** (`backend/app/db`): SQLite persistence for conversation records
- **Core layer** (`backend/app/core`): config and logging

## Data flow

1. Client sends `POST /chat` with a user message.
2. API route calls `BrainService`.
3. `BrainService` selects provider (`echo` or `ollama`).
4. User message is persisted and passed through memory extraction.
5. Structured memories are persisted in SQLite.
6. Assistant response is generated and persisted in SQLite.
7. API returns structured chat response.

## Local-first policy

- Database is local (`data/project_we.db` by default).
- No network calls unless provider is explicitly set to `ollama`.
- Provider can be replaced without changing memory storage format.

## Next milestones

- Document ingestion + semantic retrieval
- Voice I/O module
- Desktop client (Tauri + React)
