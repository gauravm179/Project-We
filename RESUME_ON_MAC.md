# Resume work on your Mac

All work is saved on GitHub **`main`** (also on `feature/v0.2-memory`).

Last saved: **0.3.4** — **shared local learnings for all bots** (SQLite `bot_learnings` +
`data/bot_learnings/`). Master, coding-bot, and web-learner-bot store notes and recall them
next time. Also keeps multi-chart curriculum (0.3.3) and instant TradingView teach.

## Shared learnings (all bots)

Ask:

`i want for all bots to learn new learnings and store them locally so they can refer next time`

Or just restart uvicorn (bootstrap enables it automatically).

Then:

`remember that I prefer the 1-hour timeframe`

Later any bot should see it under **STORED LOCAL LEARNINGS**. List via `GET /learnings`.

## Chart curriculum (local skills on the laptop)

Ask in Voice:

`i want a bot to learn reading all types of chart and store all skills locally on laptop`

Expected: installs/refreshes skills, lists chart types, path like `…/data/chart_curriculum/`.

Then ask: `teach me Heikin-Ashi` or `learn how to read trade charts`.

## Start (kill old server first)

```bash
# Stop ANY old uvicorn (Ctrl+C in its Terminal, or:)
pkill -f 'uvicorn app.main:app' || true

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

# Prefer NO --reload so you always know which process is live
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **one** Voice tab: http://127.0.0.1:8000/ui/voice.html  
Hard-refresh (Cmd+Shift+R). Stamp must say **Server 0.3.4** and `chart_fast_path=true`.

Prove it:

```bash
curl -s http://127.0.0.1:8000/health | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["version"], d.get("chart_fast_path"), d.get("shared_local_learnings"))'
# Expect: 0.3.4 True True
```

## TradingView / “learn how to read trade charts”

Paste something like:

`https://www.tradingview.com/chart/. Can you go through website use the web bot and learn how to read trade charts`

Expected:
- Reply in **~1 second** with a candlestick lesson (`[via Web Learner]…`)
- Terminal: `MIDDLEWARE POST /voice/command` then `voice/command fast-chart-lesson`
- **Not** HTTP 500, and **not** a 100s DuckDuckGo hang

The live TradingView JS chart canvas is not readable as HTML; the web-learner teaches from a local chart skill pack for this ask. Approve internet later if you want stored tutorial-page notes.

## After you ask (non-chart)

Terminal should show:
`MIDDLEWARE POST /voice/command received`  
`voice/command start: …`  

| Ask type | Model |
|----------|--------|
| Casual chat | `qwen2.5:1.5b` |
| Coding / deep tech | `deepseek-r1:8b` |

## What was built

- Master auto-routes to coding-bot / web-learner-bot
- Chart/TradingView teach asks → instant local lesson (0.3.1+)
- Multi-chart curriculum install on laptop (`data/chart_curriculum/` + SQLite) (0.3.3+)
- `/voice/command` soft-fails with HTTP 200 + reply text (0.3.1+)
- Chat/voice “yes approved” grants internet and retries
- Health exposes `chart_fast_path` + `voice_command_always_200` (0.3.2+)

## Quick health check

```bash
curl -s http://127.0.0.1:8000/health
curl -s 'http://127.0.0.1:8000/health?probe=1'   # force live Ollama ping
```
