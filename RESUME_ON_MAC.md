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

## What was built

- Coding-bot under master assistant
- Browser chat UI + notes
- Mistake learning + guidelines when stuck
- Local Llama/Ollama support
- 54 tests passing
