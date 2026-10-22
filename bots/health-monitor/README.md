# health-monitor

A morning health report from a Xiaomi Mi Band: sleep, resting heart rate, steps, SpO2 and stress are exported with
Gadgetbridge, analysed by Claude and sent to your Telegram with an overall score. Russian-language report prompt.

**Stack:** Python 3.12, python-telegram-bot, SQLite (Gadgetbridge export), Anthropic API or `claude` CLI.

```text
Bot:  Health Report | 2026-03-20
      Overall: 78% - Good
      Sleep 7h10, deep 19% - fine. Resting HR 58. Steps 6 400 - below target. SpO2 96%. Stress 41.
```

## Run
```bash
cp .env.example .env      # HEALTH_BOT_TOKEN, CHAT_ID, ANTHROPIC_API_KEY, USER_PROFILE
python3 main.py --demo --dry-run --api   # fake data, prints the report, sends nothing
docker compose up -d --build health-monitor   # from the repo root: inline-button bot (owner only)
```
Real data: either put an exported `Gadgetbridge.db` into `data/gadgetbridge.db` (`python3 main.py --local`), or let the
phone sync over an SSH tunnel (Termux, alias in `PHONE_SSH_HOST`). For a daily report add `run.sh` to cron.
The bot only answers `CHAT_ID`. Health data is sent to the Anthropic API for analysis - mind your privacy.
