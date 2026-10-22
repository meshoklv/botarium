# salon-booking

An AI receptionist for a beauty salon: clients book by text or voice in plain language, the bot collects the
service, master, date, time, name and phone, validates them and stores the booking. Russian-language UI.
A demo for small-business bots - edit services, masters and hours in `config.py`.

**Stack:** Python 3.12, python-telegram-bot 21.5, SQLite, OpenRouter LLM, Groq Whisper.

```text
Client: "Hi, a manicure with Maria tomorrow around two?"
Bot:    Tomorrow at 14:00 with Maria - manicure, 60 min, 2000 RUB. What's your name and phone number?
Client: Olga, +7 900 000 00 00
Bot:    Booked. See you tomorrow at 14:00!   (/my_bookings, /cancel)
```

## Run
```bash
cp .env.example .env      # TELEGRAM_BOT_TOKEN, OUTER_API_KEY, GROQ_API_KEY, SALON_NAME
docker compose up -d --build salon-booking   # from the repo root
```
Note: the services/masters list also appears inside the system prompt in `config.py` - keep both in sync.
The bot does not know real availability; it records requests only.
