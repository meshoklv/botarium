# grumpy-reminder

A reminder bot that nags you with an aggressive, profane personality until you mark the task done.
Russian-language UI, strong language by design.

**Stack:** Python 3.12, python-telegram-bot 21.5, APScheduler, SQLite, OpenRouter LLM, Groq Whisper.

```text
You:  [voice] "remind me tomorrow at 9 to call the bank"
Bot:  Got it. Tomorrow 09:00 - call the bank. [Snooze 5/15/30/60] [Cancel]
...next day, 09:00
Bot:  (loudly) Time to call the bank! Do it NOW.   -> repeats at +5 / +10 min, escalates if ignored
```

Understands natural language and voice, detects your timezone from a city name (`/timezone`).

## Run
```bash
cp .env.example .env      # TELEGRAM_BOT_TOKEN, OUTER_API_KEY (OpenRouter), GROQ_API_KEY
docker compose up -d --build grumpy-reminder   # from the repo root
# or: pip install -r requirements.txt && python bot.py
```
