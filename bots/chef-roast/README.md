# chef-roast

"What should I cook?" - a recipe bot with the personality of an angry TV chef. Russian-language UI,
profanity depends on the mode (`light` / `standard` / `ramsey`).

**Stack:** Node.js 22, Telegraf, SQLite, OpenRouter LLM. Includes a basic food-safety filter for dangerous ingredients.

```text
You:  I have eggs, tomatoes and stale bread
Bot:  (in character) Fine, shakshuka-style toast. Heat the pan. HEAT. THE. PAN. Step 1: ...
```

## Run
```bash
cp .env.example .env      # TELEGRAM_BOT_TOKEN, OPENROUTER_API_KEY
docker compose up -d --build chef-roast   # from the repo root
# or: npm ci && npm start
```
