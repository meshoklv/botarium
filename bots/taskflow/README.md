# taskflow

Task manager in Telegram: projects, deadlines, tags, invites, recurring tasks, voice input and AI task analysis.
Russian-language UI.

**Stack:** Python 3.12, python-telegram-bot 20.3, PostgreSQL, APScheduler, whisper.cpp (local speech recognition), OpenRouter LLM.

```text
You:  [voice] "Remind the team to send the invoice by Thursday, high priority"
Bot:  New task: Send the invoice - deadline Thursday - priority high
      [Done] [Edit] [AI analysis]
```

An optional "design team" mode (orders, dashboard) turns on when `TEAM_USER_IDS` is set.

## Run
```bash
cp .env.example .env      # TELEGRAM_BOT_TOKEN, OPENROUTER_API_KEY
docker compose up -d --build taskflow   # from the repo root: starts the bot + Postgres (schema from sql/)
```
Without Docker: apply `sql/*.sql` to your Postgres in order, set `DATABASE_URL`, run `make setup-speech` for voice
recognition (optional), then `python bot.py`.
`backup_database.py` / `restore_database.py` dump and restore all tables as JSON.
