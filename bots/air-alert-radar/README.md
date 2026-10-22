# air-alert-radar

Personal Telegram alerts about air threats (drones, missile danger, air defence activity) for a region you choose.
Russian-language UI. Zero dependencies - Python standard library only.

**Sources:** radar-russia.ru (SSE), radar-map.ru, bplarussia.ru, public t.me channels. Alerts are classified by
distance to your home point (red / orange / yellow / all-clear) and de-duplicated across sources.

```text
Bot:  RED  BPLA - Khimki / Zelenograd
      > Drone danger reported over Khimki
      14:05 MSK - radar-russia.ru     [Map] [Quiet 1h] [Got it]
```
Private by design: strangers get no reply; their first message goes to you as an approve/reject card.

## Configure and run
```bash
cp config.example.json config.json   # token, your Telegram id, home coordinates, place names (regex stems)
docker compose up -d --build air-alert-radar   # from the repo root
# or: python3 bot.py   (without a token it runs in dry-run mode and only logs events)
```
`BOT_TOKEN`, `ADMIN_ID`, `HOME_LAT`, `HOME_LON` env vars override the config. The sample config is an
example for the Moscow region - replace the area and the matching patterns with your own.

> [!WARNING]
> Sources are unofficial OSINT aggregators: expect misses and false alarms. This is a supplement to official
> warnings (sirens, SMS), never a replacement.
