# voice-summarizer

Send a voice message, get a clean written summary. Russian-language UI.

**Stack:** Python 3.12, python-telegram-bot 21.5, Groq Whisper (speech-to-text), OpenRouter LLM (summaries).

```text
You:  [voice message, 2 min]
Bot:  Transcribing and summarizing...
Bot:  Key points: the delivery moves to Friday; the budget stays; Anna will send the contract.
You:  [tap "Make it shorter"]
Bot:  - Delivery: Friday  - Budget: unchanged  - Contract: Anna
```

Two modes: **instant note** (any voice message gets an impersonal summary) and **story session**
(name a speaker, forward several voice messages, get one summary "what <name> said").

## Run
```bash
cp .env.example .env      # TELEGRAM_BOT_TOKEN, OUTER_API_KEY (OpenRouter), GROQ_API_KEY
docker compose up -d --build voice-summarizer   # from the repo root
# or: pip install -r requirements.txt && python bot.py
```
Set `ALLOWED_USER_IDS` to restrict the bot to yourself - otherwise anyone who finds it spends your API quota.
