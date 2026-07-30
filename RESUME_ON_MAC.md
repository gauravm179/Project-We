# Resume work on your Mac

All work is saved on GitHub **`main`** (also on `feature/v0.2-memory` and `cursor/coding-bot-training-c355`).

Last saved: **Qwen for conversation**, **DeepSeek for deep technical**; voice + routing + SQLite lock fixes.

## Tomorrow — start here (dual models)

```bash
cd ~/Project-We
git checkout main
git pull origin main

cd backend
source .venv/bin/activate

export PROJECT_WE_PROVIDER=ollama
export PROJECT_WE_OLLAMA_CHAT_MODEL=qwen2.5:1.5b
export PROJECT_WE_OLLAMA_TECH_MODEL=deepseek-r1:8b
export PROJECT_WE_OLLAMA_MODEL=qwen2.5:1.5b
export PROJECT_WE_OLLAMA_AUTO_ROUTE_MODELS=true
export PROJECT_WE_OLLAMA_REASONING=false
export PROJECT_WE_OLLAMA_NUM_PREDICT=256
export PROJECT_WE_OLLAMA_KEEP_ALIVE=30m
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Routing (automatic):**

| Kind of ask | Model |
|-------------|--------|
| Hello / casual chat / simple questions | `qwen2.5:1.5b` (fast) |
| Coding, debug, algorithms, complex tech | `deepseek-r1:8b` (deeper) |
| Coding specialist (`coding-bot`) | always DeepSeek |
| Web learner | Qwen unless the ask is clearly technical |

Say **“use qwen”** or **“use deepseek”** to nudge routing.

Disable auto-route (single model only):

```bash
export PROJECT_WE_OLLAMA_AUTO_ROUTE_MODELS=false
export PROJECT_WE_OLLAMA_MODEL=qwen2.5:1.5b
```

First reply after idle can be slower (model load); later ones are faster with keep_alive. Switching to DeepSeek the first time also loads that model.

Open:

- Home: http://127.0.0.1:8000/
- Voice: http://127.0.0.1:8000/ui/voice.html
- Coding: http://127.0.0.1:8000/ui/
- Web learner: http://127.0.0.1:8000/ui/web-learner.html

On voice page: **Start listening** or type a question. Wake-word is optional (needs Python 3.12).

## Models already on this Mac (Ollama)

Checked via `curl http://127.0.0.1:11434/api/tags`:

- `qwen2.5:1.5b` ← conversation / fast
- `deepseek-r1:8b` ← deep technical / coding

Ollama CLI may be missing from PATH, but the service on port **11434** works.

## What was built

- Master bot auto-routes to coding-bot / web-learner-bot
- Ollama auto-picks Qwen vs DeepSeek per message
- Voice UI (browser mic + text box)
- Web search + page capture
- Coding bot with skills + mistake learning
- SQLite WAL + lighter SOS middleware (fixes `database is locked`)

## Python 3.14 notes

- Do **not** require `onnxruntime` / wake-word on 3.14
- Browser mic + typing work without `[voice-wake]`
- Full wake-word later: new venv with **Python 3.12** + `pip install -e '.[voice,voice-wake,voice-stt]'`

## Quick health check

```bash
curl -s http://127.0.0.1:8000/health
# look for chat_model, tech_model, auto_route_models
curl -s http://127.0.0.1:11434/api/tags
```
