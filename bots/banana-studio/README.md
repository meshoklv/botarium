# banana-studio

Image generation, editing and style transfer in Telegram on top of Nano Banana (via kie.ai), with daily limits,
subscription tiers and an admin panel. Russian-language UI.

**Stack:** Python 3.12, python-telegram-bot 21.5, aiohttp, SQLite, kie.ai API.

```text
You:  "a corgi astronaut on the moon, film still"
Bot:  Aspect ratio: [Auto: 16:9] [1:1] [3:4] [9:16]
Bot:  [image]   [Regenerate] [Edit prompt]
```
Modes: **generate**, **edit** (send a photo + describe the change), **reference** (apply the style of one image to another).
Limits per day: free / plus / ultra (configurable). Tiers are granted by the admin; there is no payment integration.

## Run
```bash
cp .env.example .env      # TELEGRAM_BOT_TOKEN, KIE_API_KEY, ADMIN_USER_ID
docker compose up -d --build banana-studio   # from the repo root
```
The admin (`ADMIN_USER_ID`) gets stats, subscription grants and broadcasts. Without it the admin panel is disabled.
