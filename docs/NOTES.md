# Project We — Agent Notes

Working notes for system configuration, bot hierarchy, and how to run the project smoothly.

---

## 1. System configuration

### Runtime environment (cloud dev)

| Item | Value |
|------|-------|
| Python | 3.12+ |
| Virtualenv | `backend/.venv` |
| Database | SQLite at `data/project_we.db` (gitignored) |
| Default provider | `echo` (no network, good for tests) |
| Ollama provider | Set `PROJECT_WE_PROVIDER=ollama` |

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PROJECT_WE_PROVIDER` | `echo` | AI backend: `echo` or `ollama` |
| `PROJECT_WE_DATABASE_URL` | `sqlite:///.../data/project_we.db` | Database location |
| `PROJECT_WE_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama API URL |
| `PROJECT_WE_OLLAMA_MODEL` | `qwen2.5:7b` | Ollama model name |
| `PROJECT_WE_STRICT_LOCAL_MODE` | `true` | Enforce local-first policy |
| `PROJECT_WE_INTERNET_MODE` | `ask` | `ask`, `never`, or `always` |

### Dev commands

```bash
cd backend
source .venv/bin/activate
pip install -e ".[dev]"
pytest          # run tests
ruff check .    # lint
uvicorn app.main:app --reload   # start API on :8000
```

API docs: http://127.0.0.1:8000/docs

**Agent notes (always available in browser):**

- Notes page: http://127.0.0.1:8000/ui/notes.html
- Notes API: http://127.0.0.1:8000/notes
- Raw markdown: http://127.0.0.1:8000/notes/raw

---

## 2. How bots work

Project We uses a **master bot + specialist sub-bots** model.

```
Master Bot (Project We)     POST /chat
 │
 ├── coding-bot             POST /specialists/coding-bot/chat
 ├── trading-bot            (user-created)
 ├── troubleshoot-bot       (user-created)
 └── ...                    (user-created)
```

### Master bot

- Entry point: `POST /chat`
- Handles general assistant tasks
- Uses shared memory (facts, preferences, tasks)
- Can gate internet access via permission requests

### Specialist sub-bots

Each specialist has:

| Field | What it controls |
|-------|------------------|
| `slug` | Unique ID (e.g. `coding-bot`) |
| `name` | Display name |
| `sector` | Domain label (e.g. `coding`) |
| `system_prompt` | Personality and expertise |
| `description` | Short summary |

Each specialist keeps **its own chat history** but shares the **global memory store**.

### Training (learnable skills)

"Training" a bot means assigning **skills** to it:

1. **Define** a skill template (`POST /skills`)
2. **Teach** it to a bot (`POST /specialists/{slug}/skills`) → status: `learning`
3. **Activate** it (`POST /skills/assignments/{id}/activate`) → status: `active`
4. Active skills are injected into every reply under `--- LEARNED SKILLS ---`

Skill lifecycle: `learning` → `active` → (optional) `paused`

Only **active** skills affect chat responses.

---

## 3. Coding bot (bootstrapped)

On every app startup, `backend/app/bootstrap.py` automatically:

1. Creates `coding-bot` if it does not exist (or refreshes its profile)
2. Registers five coding skills
3. Assigns each skill to `coding-bot`
4. Activates all five skills

### Coding bot profile

| Field | Value |
|-------|-------|
| Slug | `coding-bot` |
| Name | Code Assistant |
| Sector | `coding` |
| Role | Expert software engineer under the master assistant |

### Trained skills (all active on startup)

| Skill slug | Purpose | Parameters |
|------------|---------|------------|
| `code-review` | Review for bugs, security, maintainability | `language=python`, `focus=correctness` |
| `write-tests` | Generate pytest-style tests | `framework=pytest`, `coverage_goal=critical paths` |
| `debug-errors` | Diagnose stack traces and logs | `runtime=python`, `log_source=user-provided` |
| `refactor-code` | Improve structure with minimal diffs | `style=minimal-diff` |
| `build-logic` | Design algorithms and build features from requirements | all supported languages |

### Supported languages (18)

Python, JavaScript, TypeScript, Java, C#, C++, C, Go, Rust, Ruby, PHP, Swift, Kotlin, SQL, Bash/Shell, HTML/CSS, R, Scala.

The bot is trained to **understand logic** (algorithms, control flow, debugging) and **build features** (scaffold modules, APIs, tests, UI wiring).

### Learn from mistakes

Teach the bot corrections with:

```bash
curl -X POST http://127.0.0.1:8000/specialists/coding-bot/feedback \
  -H 'Content-Type: application/json' \
  -d '{
    "mistake": "Said mutable defaults are fine",
    "correction": "Use None and create the object inside the function",
    "language": "python"
  }'
```

Lessons are stored and injected into future coding-bot replies.

### Internet guidelines when stuck

- Local curated guidelines (PEP 8, MDN, Go, Rust, etc.) are used automatically when the bot detects you are stuck.
- Live internet docs require consent: ask with words like `latest online guidelines`, then approve via `POST /permissions/{id}/decision`.
- Browser UI has **Teach coding-bot** and **Approve internet** controls.

### Verify coding bot

```bash
# Open local browser UI
open http://127.0.0.1:8000/ui/

# Or check supported languages and capabilities
curl http://127.0.0.1:8000/specialists/coding-bot/capabilities

# See trained skills
curl http://127.0.0.1:8000/specialists/coding-bot/skills

# Chat with coding bot
curl -X POST http://127.0.0.1:8000/specialists/coding-bot/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Review this Python function for bugs"}'
```

---

## 4. Memory (shared notes across bots)

All bots share structured memory extracted from user messages:

| Type | Example trigger |
|------|-----------------|
| `fact` | "My name is Alex" |
| `preference` | "I prefer macOS" / "I like dark mode" |
| `task` | "Remind me to fix the login bug" |

Endpoints:

- `GET /memory` — list stored memories
- `GET /memory/summary` — counts by type

Memory is **not** the same as chat history. Chat history is per-bot; memory is global.

---

## 5. Local browser UI

| Page | URL | Purpose |
|------|-----|---------|
| Code Assistant chat | http://127.0.0.1:8000/ui/ | Chat with `coding-bot` |
| Agent notes | http://127.0.0.1:8000/ui/notes.html | Full notes (this document) |
| API docs | http://127.0.0.1:8000/docs | Swagger UI |

Notes are **served live** from `docs/NOTES.md` by the backend — they do not disappear when you restart the server as long as the file exists in the repo.

---

## 6. Branch and PR status

| Item | Value |
|------|-------|
| Base branch | `feature/v0.2-memory` |
| Feature branch | `cursor/coding-bot-training-c355` |
| PR | #4 — bootstrap trained coding-bot |
| Tests | 45+ passing |

---

## 7. What's not built yet

- Specialist auto-routing (master bot picking the right sub-bot automatically)
- Skill auto-suggestion from conversation
- Document/codebase ingestion for coding bot context
- Desktop UI (Tauri + React) — API only for now
- Stronger coding models (recommend `deepseek-coder` or `qwen2.5-coder` via Ollama)

---

## 8. Quick reference: add a new trained bot

```bash
# 1. Create the specialist
curl -X POST http://127.0.0.1:8000/specialists \
  -H 'Content-Type: application/json' \
  -d '{
    "slug": "my-bot",
    "name": "My Bot",
    "sector": "custom",
    "system_prompt": "You are an expert in ..."
  }'

# 2. Define a skill
curl -X POST http://127.0.0.1:8000/skills \
  -H 'Content-Type: application/json' \
  -d '{
    "slug": "my-skill",
    "name": "My Skill",
    "category": "custom",
    "instructions": "When asked, do ..."
  }'

# 3. Teach the skill to the bot
curl -X POST http://127.0.0.1:8000/specialists/my-bot/skills \
  -H 'Content-Type: application/json' \
  -d '{"skill_slug": "my-skill", "parameters": {}}'

# 4. Activate (use assignment id from step 3 response)
curl -X POST http://127.0.0.1:8000/skills/assignments/1/activate
```
