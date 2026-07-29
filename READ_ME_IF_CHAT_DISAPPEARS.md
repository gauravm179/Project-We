# IF CURSOR CHAT DISAPPEARS — READ THIS

Chat messages in Cursor Cloud can vanish from the UI.  
**Use these permanent links instead:**

1. **PR (main permanent notes):** https://github.com/gauravm179/Project-We/pull/4  
2. **Agent transcript:** https://cursor.com/agents/bc-17c6d158-a2a6-44cc-8521-a322a991c355  
3. **Repo notes file:** `docs/NOTES.md`  
4. **Browser notes (after starting server):** http://127.0.0.1:8000/ui/notes.html  

## Start server
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

## Coding bot
- URL: http://127.0.0.1:8000/ui/
- Skills: code-review, write-tests, debug-errors, refactor-code, build-logic
- Languages: Python, JS, TS, Java, C#, C++, C, Go, Rust, Ruby, PHP, Swift, Kotlin, SQL, Bash, HTML/CSS, R, Scala
- Learns from mistakes via `/specialists/coding-bot/feedback`
- Uses local guidelines when stuck; live internet docs need permission approval
