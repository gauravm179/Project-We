# Resume work on your Mac

All work is saved on GitHub **`main`** (also on `feature/v0.2-memory`).

Last saved: quieter Terminal polls, faster chart/web asks, chat **yes/approved** internet retry, Qwen/DeepSeek routing.

## Start (fast + dual models)

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

Open **one** Voice tab only: http://127.0.0.1:8000/ui/voice.html  
(Extra tabs spam `/voice/status` in Terminal.)

After you ask a question, Terminal should show:
`voice/command start: …`  
Access log `POST /voice/command` appears only when the reply finishes (can take 30–90s for web + model).

For TradingView: reply **yes approved** once for internet. The bot searches chart tutorials (it cannot read the live JS chart canvas).

| Ask type | Model |
|----------|--------|
| Casual chat | `qwen2.5:1.5b` |
| Coding / deep tech | `deepseek-r1:8b` |

## What was built

- Master auto-routes to coding-bot / web-learner-bot
- Chat/voice “yes approved” grants internet and retries
- Health Ollama check is cached (less Terminal noise)
- Voice polls status every 60s, not health every 15s

## Quick health check

```bash
curl -s http://127.0.0.1:8000/health
curl -s 'http://127.0.0.1:8000/health?probe=1'   # force live Ollama ping
```
