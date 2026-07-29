# Resume work on your Mac

All work is saved on GitHub branch: `cursor/coding-bot-training-c355`  
PR: https://github.com/gauravm179/Project-We/pull/4

## First time on this Mac (if not cloned yet)

```bash
cd ~
git clone https://github.com/gauravm179/Project-We.git
cd Project-We
git checkout cursor/coding-bot-training-c355
git pull origin cursor/coding-bot-training-c355
```

## Every time you come back

```bash
cd ~/Project-We
git checkout cursor/coding-bot-training-c355
git pull origin cursor/coding-bot-training-c355
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Start the bot (echo stub — for UI only)

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open: http://127.0.0.1:8000/ui/ (coding bot)  
Web learner: http://127.0.0.1:8000/ui/web-learner.html

## Start with real local Llama (for maths/code answers)

```bash
ollama pull llama3.2
export PROJECT_WE_PROVIDER=ollama
export PROJECT_WE_OLLAMA_MODEL=llama3.2
export PROJECT_WE_OLLAMA_REASONING=true
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Check: http://127.0.0.1:8000/health → `"provider": "ollama"`, `"reachable": true`

## Enable Voice Bot on this Mac

### Quick mode (browser mic — recommended first)

```bash
cd ~/Project-We/backend
source .venv/bin/activate
export PROJECT_WE_PROVIDER=ollama
export PROJECT_WE_OLLAMA_MODEL=llama3.2
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open: http://127.0.0.1:8000/ui/voice.html  
1. Check **I share microphone / voice**  
2. Click **Start listening** and allow mic access in the browser  
3. Speak a command — the bot replies (and can speak aloud)

### Wake-word mode (always listening: “hey jarvis”)

```bash
cd ~/Project-We/backend
source .venv/bin/activate
pip install -e ".[voice]"
export PROJECT_WE_VOICE_ENABLED=true
export PROJECT_WE_VOICE_WAKE_WORD="hey jarvis"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Then either:
- Click **Start wake-word** on http://127.0.0.1:8000/ui/voice.html  
- Or call `POST /voice/start`

macOS: System Settings → Privacy & Security → Microphone → allow Terminal / your browser.

## What was built

- Coding-bot under master assistant
- Web-learner-bot (search + page capture)
- Voice bot (browser mic + optional wake-word)
- Browser chat UI + notes
- Mistake learning + guidelines when stuck
- Local Llama/Ollama support
- 70+ tests passing