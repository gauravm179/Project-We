# Resume work on your Mac

All work is saved on GitHub **`main`** (also on `feature/v0.2-memory` and `cursor/coding-bot-training-c355`).

Last saved: voice bot working with local Ollama model `qwen2.5:1.5b`, SQLite lock fixes, web/coding routing.

## Tomorrow — start here

```bash
cd ~/Project-We
git checkout main
git pull origin main

cd backend
source .venv/bin/activate

export PROJECT_WE_PROVIDER=ollama
export PROJECT_WE_OLLAMA_MODEL=qwen2.5:1.5b
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

- Home: http://127.0.0.1:8000/
- Voice: http://127.0.0.1:8000/ui/voice.html
- Coding: http://127.0.0.1:8000/ui/
- Web learner: http://127.0.0.1:8000/ui/web-learner.html

On voice page: **Start listening** or type a question. Wake-word is optional (needs Python 3.12).

## Models already on this Mac (Ollama)

Checked via `curl http://127.0.0.1:11434/api/tags`:

- `qwen2.5:1.5b` ← use this (faster)
- `deepseek-r1:8b` ← stronger/slower

Ollama CLI may be missing from PATH, but the service on port **11434** works.

```bash
export PROJECT_WE_OLLAMA_MODEL=deepseek-r1:8b   # optional switch
```

## What was built

- Master bot auto-routes to coding-bot / web-learner-bot
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
curl -s http://127.0.0.1:11434/api/tags
```
