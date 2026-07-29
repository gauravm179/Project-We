# Resume work on your Mac

All work is saved on GitHub:

- `main` (merged) — use this for a fresh clone
- `feature/v0.2-memory` (merged)
- Branch `cursor/coding-bot-training-c355` / PR #4 (merged into feature base)

## First time on this Mac (if not cloned yet)

```bash
cd ~
git clone https://github.com/gauravm179/Project-We.git
cd Project-We
git checkout main
git pull origin main
```

## Every time you come back

```bash
cd ~/Project-We
git checkout main
git pull origin main
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

### Quick mode (browser mic — works on Python 3.14, no ffmpeg)

```bash
cd ~/Project-We/backend
source .venv/bin/activate
export PROJECT_WE_PROVIDER=ollama
export PROJECT_WE_OLLAMA_MODEL=llama3.2
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open: http://127.0.0.1:8000/ui/voice.html  
Use **Start listening** or type a question. Do not need wake-word packages.

### Wake-word mode (optional)

Python **3.14** often fails installing `faster-whisper` (`av` / ffmpeg). Prefer one of:

**Option A — install ffmpeg, then STT:**
```bash
brew install ffmpeg
cd ~/Project-We/backend && source .venv/bin/activate
git pull origin main
pip install -e '.[voice]'
pip install -e '.[voice-stt]'
```

**Option B — use Python 3.12 (recommended for full wake-word on Mac):**
```bash
brew install python@3.12
cd ~/Project-We/backend
python3.12 -m venv .venv312
source .venv312/bin/activate
pip install -U pip
pip install -e '.[dev,voice,voice-wake,voice-stt]'
```

Note: Python **3.14** cannot install `onnxruntime` / `openwakeword` yet.
On 3.14 just run the app — browser mic + typed questions work with **no** `[voice]` extras.

Then:
```bash
export PROJECT_WE_VOICE_ENABLED=true
export PROJECT_WE_VOICE_WAKE_WORD="hey jarvis"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Allow Microphone for Terminal in macOS Privacy settings.

## What was built

- Coding-bot under master assistant
- Web-learner-bot (search + page capture)
- Voice bot (browser mic + optional wake-word)
- Browser chat UI + notes
- Mistake learning + guidelines when stuck
- Local Llama/Ollama support
- 70+ tests passing