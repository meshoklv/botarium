#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
БПЛА-Радар — персональный бот-оповещатель о воздушных угрозах
для заданного района (координаты и названия населённых пунктов — в config.json).

Источники:
  1. radar-russia.ru  /api/stream (SSE, реалтайм) с фолбэком на /api/state
  2. radar-map.ru     /api/state  (поллинг)
  3. bplarussia.ru    WordPress REST API, категория региона (bplarussia_category)
  4. t.me/s/<канал>   веб-превью радар-каналов Telegram

Только стандартная библиотека Python. Работает под PM2.
Без токена в config.json — dry-run: события пишутся в лог, никуда не шлются.
"""

import json, re, os, sys, time, html, sqlite3, threading, queue, logging, random
import urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
_CFG_PATH = os.path.join(BASE, "config.json")
CFG = json.load(open(_CFG_PATH, encoding="utf-8")) if os.path.exists(_CFG_PATH) else {}
# env overrides (handy for Docker): BOT_TOKEN, ADMIN_ID, HOME_LAT, HOME_LON
for _k, _env, _cast in (("bot_token", "BOT_TOKEN", str), ("admin_id", "ADMIN_ID", int),
                        ("home_lat", "HOME_LAT", float), ("home_lon", "HOME_LON", float)):
    if os.environ.get(_env):
        CFG[_k] = _cast(os.environ[_env])
MSK = timezone(timedelta(hours=3))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) personal-alert-bot"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger("bpla")

# ---------------------------------------------------------------- база

db_lock = threading.Lock()
db = sqlite3.connect(os.environ.get("STATE_DB", os.path.join(BASE, "state.db")), check_same_thread=False)
db.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)")
db.execute("CREATE TABLE IF NOT EXISTS seen (source TEXT, key TEXT, ts INTEGER, PRIMARY KEY(source,key))")
db.execute("CREATE TABLE IF NOT EXISTS gists (gist TEXT PRIMARY KEY, ts INTEGER)")
db.execute("""CREATE TABLE IF NOT EXISTS events
              (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, level TEXT,
               kind TEXT, clear INTEGER, text TEXT, source TEXT, sent INTEGER)""")
db.execute("""CREATE TABLE IF NOT EXISTS users
              (id INTEGER PRIMARY KEY, status TEXT, name TEXT, username TEXT, ts INTEGER)""")
db.commit()

def kv_get(k, default=None):
    with db_lock:
        row = db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return row[0] if row else default

def kv_set(k, v):
    with db_lock:
        db.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (k, str(v)))
        db.commit()

def seen_check_add(source, key):
    """True если ключ новый (и тогда он записывается)."""
    with db_lock:
        row = db.execute("SELECT 1 FROM seen WHERE source=? AND key=?", (source, key)).fetchone()
        if row:
            return False
        db.execute("INSERT INTO seen VALUES (?,?,?)", (source, key, int(time.time())))
        db.execute("DELETE FROM seen WHERE ts < ?", (int(time.time()) - 7 * 86400,))
        db.commit()
        return True

DEFAULT_SETTINGS = {"orange": 1, "yellow": 1, "moscow": 1, "clears": 1, "night_silent": 1}

def get_settings():
    s = json.loads(kv_get("settings", "{}"))
    return {**DEFAULT_SETTINGS, **s}

def set_setting(k, v):
    s = get_settings(); s[k] = v
    kv_set("settings", json.dumps(s))

# ---------------------------------------------------------------- гео и типы угроз

# Зоны задаются в config.json (см. config.example.json):
#   red_patterns    - основы слов (lowercase, ё->е) для «нашего района»
#   orange_places   - {"Название": "regex"} соседние округа
#   region_label / region_patterns - вся область (жёлтый уровень)
HOME_LABEL = CFG.get("home_label", "Home area")
RED_RE = re.compile("|".join(CFG.get("red_patterns") or ["(?!x)x"]))
ORANGE_LIST = [(n, p) for n, p in (CFG.get("orange_places") or {}).items()]
REGION_LABEL = CFG.get("region_label", "Region")
YELLOW_RE = re.compile(CFG.get("region_patterns") or r"(?!x)x")
CAPITAL_LABEL = CFG.get("capital_label", "Москва")
MOSCOW_RE = re.compile(CFG.get("capital_pattern") or r"москв")
MO_ABBR_RE = re.compile(r"\bМО\b(?!\s*РФ)")  # «МО Истра» — область, «МО РФ» — министерство

KIND_MISSILE = re.compile(r"ракетн|ракета|ракеты|баллистич|искандер|кинжал|крылат")
KIND_UAV = re.compile(r"бпла|беспилотн|дрон|геран|мопед")
KIND_AVIA = re.compile(r"авиац|уаб|фаб|каб")
KIND_ALARM = re.compile(r"воздушн\S*\s+тревог")
CLEAR_RE = re.compile(r"отбой|отмена\s+(опасност|тревог)")
KIND_NAMES = {"missile": "РАКЕТНАЯ ОПАСНОСТЬ", "uav": "БПЛА", "aviation": "Авиация/УАБ",
              "alarm": "Воздушная тревога", "pvo": "Работа ПВО", "other": "Угроза"}

def norm(text):
    return text.replace("ё", "е").replace("Ё", "Е").lower()

HOME_LAT, HOME_LON = CFG.get("home_lat", 55.7558), CFG.get("home_lon", 37.6173)
RED_KM = CFG.get("red_radius_km", 15)
ORANGE_KM = CFG.get("orange_radius_km", 50)

def km_from_home(lat, lon):
    import math
    dlat = math.radians(lat - HOME_LAT)
    dlon = math.radians(lon - HOME_LON)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(HOME_LAT)) * math.cos(math.radians(lat)) * math.sin(dlon / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(a))

def classify_geo(text):
    """-> (level, label). level: red / orange / yellow / none"""
    n = norm(text)
    if RED_RE.search(n):
        return "red", HOME_LABEL
    for name, pat in ORANGE_LIST:
        if re.search(pat, n):
            return "orange", name
    if YELLOW_RE.search(n) or MO_ABBR_RE.search(text):
        return "yellow", REGION_LABEL
    if MOSCOW_RE.search(n):
        return "yellow", CAPITAL_LABEL
    return "none", ""

def classify_kind(text, api_kind=None):
    n = norm(text)
    if api_kind in ("missile", "rocket") or KIND_MISSILE.search(n):
        return "missile"
    if api_kind == "uav" or KIND_UAV.search(n):
        return "uav"
    if api_kind in ("aviation", "uab") or KIND_AVIA.search(n):
        return "aviation"
    if "пво" in n:
        return "pvo"
    if KIND_ALARM.search(n):
        return "alarm"
    return "other"

def is_clear(text, api_status=None):
    return api_status == "clear" or bool(CLEAR_RE.search(norm(text)))

# ---------------------------------------------------------------- Telegram Bot API

TOKEN = CFG.get("bot_token", "")
API = f"https://api.telegram.org/bot{TOKEN}/" if TOKEN else None
ADMIN_ID = CFG.get("admin_id", 0)

def user_status(uid):
    if uid == ADMIN_ID:
        return "admin"
    with db_lock:
        row = db.execute("SELECT status FROM users WHERE id=?", (uid,)).fetchone()
    return row[0] if row else None

def set_user_status(uid, status, name="", username=""):
    with db_lock:
        db.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?,?)",
                   (uid, status, name, username, int(time.time())))
        db.commit()

def recipients():
    """Кому шлём алерты: админ + одобренные."""
    with db_lock:
        rows = db.execute("SELECT id FROM users WHERE status='approved'").fetchall()
    return [ADMIN_ID] + [r[0] for r in rows]
send_lock = threading.Lock()
_last_send = [0.0]

def tg_call(method, payload, timeout=30):
    if not API:
        return None
    data = json.dumps(payload).encode()
    req = urllib.request.Request(API + method, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=timeout))
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        log.error("tg %s HTTP %s: %s", method, e.code, body)
        if e.code == 429:
            try:
                time.sleep(json.loads(body)["parameters"]["retry_after"] + 1)
            except Exception:
                time.sleep(5)
        return None
    except Exception as e:
        log.error("tg %s: %s", method, e)
        return None

def tg_send(chat_id, text, reply_markup=None, silent=False):
    with send_lock:
        gap = time.time() - _last_send[0]
        if gap < 1.5:
            time.sleep(1.5 - gap)
        _last_send[0] = time.time()
    payload = {"chat_id": chat_id, "text": text[:4090], "parse_mode": "HTML",
               "disable_web_page_preview": True, "disable_notification": silent}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg_call("sendMessage", payload)

MAIN_KB = {"keyboard": [[{"text": "📊 Статус"}, {"text": "📜 Последние события"}],
                        [{"text": "⚙️ Настройки"}, {"text": "🔕 Тихо 1 час"}]],
           "resize_keyboard": True, "is_persistent": True}

def alert_buttons():
    return {"inline_keyboard": [[
        {"text": "🗺 Карта", "url": "https://radar-map.ru"},
        {"text": "🔕 Тихо 1 ч", "callback_data": "mute60"},
        {"text": "✅ Понял", "callback_data": "ack"}]]}

# ---------------------------------------------------------------- очередь и отправка алертов

alerts_q = queue.Queue()
started_at = time.time()
src_health = {}  # источник -> unix ts последнего успешного обращения

def gist_recent(gist, cooldown):
    now = int(time.time())
    with db_lock:
        row = db.execute("SELECT ts FROM gists WHERE gist=?", (gist,)).fetchone()
        if row and now - row[0] < cooldown:
            return True
        db.execute("INSERT OR REPLACE INTO gists VALUES (?,?)", (gist, now))
        db.execute("DELETE FROM gists WHERE ts < ?", (now - 86400,))
        db.commit()
        return False

def fmt_alert(level, kind, clear, text, source, label):
    t = datetime.now(MSK).strftime("%H:%M")
    body = html.escape(text.strip())[:800]
    kind_name = KIND_NAMES.get(kind, "Угроза")
    if clear:
        head = f"🟢 <b>ОТБОЙ — {html.escape(label)}</b>"
    elif level == "red":
        head = ("🔴🔴🔴 <b>НАШ РАЙОН!</b> 🔴🔴🔴\n"
                f"‼️ <b>{kind_name} — {html.escape(label)}</b> ‼️")
    elif level == "orange":
        head = f"🟠 <b>Рядом: {html.escape(label)} — {kind_name}</b>"
    else:
        head = f"🟡 <b>{html.escape(label)} — {kind_name}</b>"
    return f"{head}\n<blockquote>{body}</blockquote>\n🕐 {t} МСК · {source}"

def dispatch_alert(level, kind, clear, text, source, label):
    """Фильтры настроек, дедуп-суть, отправка."""
    s = get_settings()
    now = int(time.time())
    with db_lock:
        db.execute("INSERT INTO events (ts,level,kind,clear,text,source,sent) VALUES (?,?,?,?,?,?,0)",
                   (now, level, kind, int(clear), text[:500], source))
        db.commit()

    if clear and not s["clears"] and level not in ("red", "orange"):
        return
    if level == "orange" and not s["orange"]:
        return
    if level == "yellow":
        if label == CAPITAL_LABEL and not s["moscow"]:
            return
        if label != CAPITAL_LABEL and not s["yellow"]:
            return

    cooldown = {"red": 300, "orange": 600, "yellow": 900}.get(level, 900)
    gist = f"{'clear' if clear else kind}|{level}|{norm(label)}"
    if gist_recent(gist, cooldown):
        if level == "red" and not clear:
            for cid in recipients():
                tg_send(cid, f"➕ <i>Подтверждение по нашему району из {source}</i>", silent=True)
        return

    muted_until = int(kv_get("muted_until", "0"))

    silent = False
    if s["night_silent"] and level != "red":
        h = datetime.now(MSK).hour
        silent = 0 <= h < 7

    msg = fmt_alert(level, kind, clear, text, source, label)
    log.info("ALERT %s/%s%s [%s] %s", level, kind, "/отбой" if clear else "", source, text[:120].replace("\n", " | "))
    if not API:
        return
    for cid in recipients():
        # «Тихо 1 час» — личная кнопка админа, гасит только его сообщения (кроме 🔴)
        if cid == ADMIN_ID and now < muted_until and level != "red":
            continue
        tg_send(cid, msg, reply_markup=None if clear else alert_buttons(), silent=silent)
    with db_lock:
        db.execute("UPDATE events SET sent=1 WHERE id=(SELECT MAX(id) FROM events)")
        db.commit()

def alert_worker():
    while True:
        item = alerts_q.get()
        try:
            dispatch_alert(*item)
        except Exception:
            log.exception("dispatch failed")

def consider(text, source, api_kind=None, api_status=None, seed=False,
             region_hint=None, coords=None):
    """Классифицировать сырое событие и поставить в очередь, если наше."""
    level, label = classify_geo(text)
    # точка не распознана по имени, но есть координаты — мерим до дома
    if level in ("none", "yellow") and coords:
        try:
            dist = km_from_home(float(coords[0]), float(coords[1]))
            if dist <= RED_KM:
                level, label = "red", f"~{int(dist)} км от дома"
            elif dist <= ORANGE_KM and level == "none":
                level, label = "orange", f"~{int(dist)} км от дома"
        except (TypeError, ValueError, IndexError):
            pass
    if level == "none":
        # источник сам сказал, что событие в МО (категория/поле региона),
        # хотя в тексте конкретный город не из наших списков (например Истра)
        if region_hint and re.search(CFG.get("region_hint_pattern") or YELLOW_RE.pattern, norm(region_hint)):
            level, label = "yellow", REGION_LABEL
        else:
            return
    kind = classify_kind(text, api_kind)
    clear = is_clear(text, api_status)
    if seed:
        return
    alerts_q.put((level, kind, clear, text, source, label))

# ---------------------------------------------------------------- HTTP помощник

def fetch(url, timeout=20, raw=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if raw else data.decode("utf-8", errors="replace")

# ---------------------------------------------------------------- источник 1: radar-russia.ru (SSE + фолбэк)

def rr_events(payload):
    evts = {}
    for e in payload.get("history", []) or []:
        if isinstance(e, dict) and "id" in e:
            evts[e["id"]] = (e, None)
    for a in payload.get("active", []) or []:
        e = a.get("lastEvent")
        if isinstance(e, dict) and "id" in e:
            evts[e["id"]] = (e, a.get("coordinates"))
    return evts

def rr_handle(payload, seed=False):
    for eid, (e, coords) in sorted(rr_events(payload).items()):
        if seen_check_add("radar-russia", str(eid)):
            regions = " ".join(e.get("regions") or [])
            # координаты меряем только у точечных событий: у region-scope
            # это центр целого региона, дистанция до дома бессмысленна
            if e.get("scope") == "region":
                coords = None
            consider(e.get("text", ""), "radar-russia.ru",
                     api_kind=e.get("kind"), api_status=e.get("status"),
                     seed=seed, region_hint=regions, coords=coords)
    src_health["radar-russia"] = time.time()

def src_radar_russia():
    # первый снапшот — только пометить как виденное, не слать старьё
    try:
        rr_handle(json.loads(fetch("https://radar-russia.ru/api/state")), seed=True)
        log.info("radar-russia: seeded")
    except Exception as e:
        log.warning("radar-russia seed: %s", e)
    while True:
        try:
            req = urllib.request.Request("https://radar-russia.ru/api/stream",
                                         headers={**UA, "Accept": "text/event-stream"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                log.info("radar-russia: SSE connected")
                buf = b""
                for chunk_line in resp:
                    if chunk_line.startswith(b"data:"):
                        buf = chunk_line[5:].strip()
                        try:
                            rr_handle(json.loads(buf))
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            log.warning("radar-russia SSE drop: %s — фолбэк на поллинг 60с", e)
            for _ in range(3):
                time.sleep(20)
                try:
                    rr_handle(json.loads(fetch("https://radar-russia.ru/api/state")))
                except Exception as e2:
                    log.warning("radar-russia poll: %s", e2)
        time.sleep(3)

# ---------------------------------------------------------------- источник 2: radar-map.ru

def rm_iter(state):
    regions = state.get("regions", {})
    items = regions.items() if isinstance(regions, dict) else [(r.get("name", ""), r) for r in regions]
    for name, r in items:
        yield name, r
    cities = state.get("cities", {})
    items = cities.items() if isinstance(cities, dict) else [(c.get("key", c.get("name", "")), c) for c in cities]
    for name, c in items:
        yield name, c

def src_radar_map(seed=False):
    interval = CFG.get("poll_radar_map_sec", 20)
    first = True
    while True:
        try:
            state = json.loads(fetch("https://radar-map.ru/api/state"))
            for name, obj in rm_iter(state):
                if not isinstance(obj, dict):
                    continue
                ts = obj.get("last_event_ts")
                txt = obj.get("source_text") or ""
                if not ts or not txt:
                    continue
                active = any(obj.get(f) for f in ("bpla", "uab", "fpv", "rocket", "aviation", "pvo"))
                if not active:
                    continue
                if seen_check_add("radar-map", f"{name}|{ts}"):
                    api_kind = "missile" if obj.get("rocket") else ("uav" if obj.get("bpla") else None)
                    hint = obj.get("region") or (name if isinstance(name, str) else "")
                    coords = None
                    if obj.get("lat") and obj.get("lon"):  # только точечные города
                        coords = (obj["lat"], obj["lon"])
                    consider(txt, "radar-map.ru", api_kind=api_kind, seed=first,
                             region_hint=hint, coords=coords)
            src_health["radar-map"] = time.time()
            if first:
                log.info("radar-map: seeded")
                first = False
        except Exception as e:
            log.warning("radar-map: %s", e)
        time.sleep(interval)

# ---------------------------------------------------------------- источник 3: bplarussia.ru (WordPress API)

TAG_RE = re.compile(r"<[^>]+>")

def src_bplarussia():
    cat = CFG.get("bplarussia_category", 13)
    interval = CFG.get("poll_bplarussia_sec", 45)
    url = (f"https://bplarussia.ru/wp-json/wp/v2/posts?categories={cat}"
           f"&per_page=10&_fields=id,date,title,content")
    first = True
    while True:
        try:
            posts = json.loads(fetch(url))
            for p in sorted(posts, key=lambda x: x["id"]):
                if seen_check_add("bplarussia", str(p["id"])):
                    title = html.unescape(TAG_RE.sub(" ", p["title"]["rendered"]))
                    body = html.unescape(TAG_RE.sub(" ", p.get("content", {}).get("rendered", "")))
                    body = re.sub(r"\s+", " ", body).strip()[:300]
                    # категория запроса = наш регион, гео гарантировано
                    consider(f"{title}\n{body}", "bplarussia.ru", seed=first,
                             region_hint=REGION_LABEL)
            src_health["bplarussia"] = time.time()
            if first:
                log.info("bplarussia: seeded")
                first = False
        except Exception as e:
            log.warning("bplarussia: %s", e)
        time.sleep(interval)

# ---------------------------------------------------------------- источник 4: t.me/s/<канал>

MSG_RE = re.compile(
    r'data-post="([^"]+)".*?tgme_widget_message_text[^>]*>(.*?)</div>', re.S)

def src_tme():
    channels = CFG.get("tme_channels", [])
    interval = CFG.get("poll_tme_sec", 75)
    first = True
    while True:
        for ch in channels:
            try:
                page = fetch(f"https://t.me/s/{ch}")
                for post_id, raw in MSG_RE.findall(page):
                    if seen_check_add("tme", post_id):
                        txt = html.unescape(TAG_RE.sub(" ", raw))
                        txt = re.sub(r"\s+", " ", txt).strip()
                        txt = re.sub(r"(❗️?\s*Радар Москва.*|🌐.*|Обход белых списков.*)", "", txt).strip()
                        if txt:
                            consider(txt, f"t.me/{ch}", seed=first)
                src_health[f"tme:{ch}"] = time.time()
            except Exception as e:
                log.warning("t.me/%s: %s", ch, e)
            time.sleep(3 + random.random() * 4)
        if first:
            log.info("t.me: seeded")
            first = False
        time.sleep(interval)

# ---------------------------------------------------------------- команды и кнопки

SET_LABELS = [
    ("orange", "🟠 Соседние округа"),
    ("yellow", f"🟡 {REGION_LABEL}"),
    ("moscow", f"🏙 {CAPITAL_LABEL}"),
    ("clears", "🟢 Отбои тревог"),
    ("night_silent", "🌙 Ночью без звука (0-7)"),
]

def settings_markup():
    s = get_settings()
    rows = [[{"text": f"{'✅' if s[k] else '❌'} {label}", "callback_data": f"tgl:{k}"}]
            for k, label in SET_LABELS]
    rows.append([{"text": "🧪 Тестовое оповещение", "callback_data": "test"}])
    return {"inline_keyboard": rows}

def cmd_status(cid):
    up = int(time.time() - started_at)
    lines = [f"🤖 <b>БПЛА-Радар</b> · работает {up // 3600}ч {up % 3600 // 60}м\n"]
    now = time.time()
    names = {"radar-russia": "radar-russia.ru (поток)", "radar-map": "radar-map.ru",
             "bplarussia": "bplarussia.ru"}
    for key, name in names.items():
        ts = src_health.get(key)
        ok = ts and now - ts < 300
        ago = f"{int(now - ts)}с назад" if ts else "ещё не отвечал"
        lines.append(f"{'🟢' if ok else '🔴'} {name} — {ago}")
    for k, ts in sorted(src_health.items()):
        if k.startswith("tme:"):
            ok = now - ts < 300
            lines.append(f"{'🟢' if ok else '🔴'} t.me/{k[4:]} — {int(now - ts)}с назад")
    with db_lock:
        n24 = db.execute("SELECT COUNT(*) FROM events WHERE ts>?", (int(now) - 86400,)).fetchone()[0]
        nred = db.execute("SELECT COUNT(*) FROM events WHERE ts>? AND level='red'",
                          (int(now) - 86400,)).fetchone()[0]
    lines.append(f"\n📈 За сутки: {n24} событий по нашей зоне, из них 🔴 по району: {nred}")
    muted = int(kv_get("muted_until", "0"))
    if now < muted:
        lines.append(f"🔕 Тишина ещё {int((muted - now) / 60)} мин (кроме 🔴)")
    tg_send(cid, "\n".join(lines), reply_markup=MAIN_KB if cid == ADMIN_ID else None)

def cmd_recent(cid):
    with db_lock:
        rows = db.execute("SELECT ts,level,kind,clear,text,source FROM events "
                          "ORDER BY id DESC LIMIT 10").fetchall()
    kb = MAIN_KB if cid == ADMIN_ID else None
    if not rows:
        tg_send(cid, "Пока тихо — событий по нашей зоне не было.", reply_markup=kb)
        return
    ico = {"red": "🔴", "orange": "🟠", "yellow": "🟡"}
    out = ["📜 <b>Последние события по нашей зоне</b>\n"]
    for ts, level, kind, clear, text, source in rows:
        t = datetime.fromtimestamp(ts, MSK).strftime("%d.%m %H:%M")
        mark = "🟢" if clear else ico.get(level, "⚪")
        first_line = html.escape(text.split(chr(10))[0][:80])
        out.append(f"{mark} {t} — {first_line} <i>({source})</i>")
    tg_send(cid, "\n".join(out), reply_markup=kb)

WELCOME = ("🛡 <b>БПЛА-Радар</b> — слежу за воздушной обстановкой вокруг "
           f"<b>{html.escape(HOME_LABEL)}</b> по 5 источникам.\n\n"
           "🔴 — наш район (всегда со звуком)\n"
           "🟠 — соседние округа\n🟡 — область/Москва\n🟢 — отбой")

def notify_admin_request(user, text):
    uid = user["id"]
    name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or "без имени"
    uname = user.get("username", "")
    who = f"{html.escape(name)}" + (f" (@{uname})" if uname else "") + f", id <code>{uid}</code>"
    kb = {"inline_keyboard": [[
        {"text": "✅ Одобрить", "callback_data": f"appr:{uid}"},
        {"text": "❌ Отклонить", "callback_data": f"deny:{uid}"}]]}
    tg_send(ADMIN_ID,
            f"🚪 <b>Стук в бота</b>\n{who}\n"
            f"<blockquote>{html.escape((text or '(не текст)')[:200])}</blockquote>"
            f"Пустить его к оповещениям?",
            reply_markup=kb)

def handle_message(msg):
    cid = msg["chat"]["id"]
    if msg["chat"].get("type") != "private":
        return
    text = (msg.get("text") or "").strip()
    status = user_status(cid)

    if status is None:
        # незнакомец: молчим ему, стучимся к админу, дальше игнор до решения
        set_user_status(cid, "pending",
                        msg.get("from", {}).get("first_name", ""),
                        msg.get("from", {}).get("username", ""))
        notify_admin_request(msg.get("from", {"id": cid}), text)
        return
    if status in ("pending", "denied"):
        return

    if text in ("/start", "/help"):
        if status == "admin":
            tg_send(cid, WELCOME + "\n\nКнопки снизу: статус, последние события, "
                                   "настройки, тишина.", reply_markup=MAIN_KB)
        else:
            tg_send(cid, WELCOME)
    elif text == "📊 Статус":
        cmd_status(cid)
    elif text == "📜 Последние события":
        cmd_recent(cid)
    elif text == "⚙️ Настройки" and status == "admin":
        tg_send(cid, "⚙️ <b>Настройки</b> — нажми, чтобы переключить:",
                reply_markup=settings_markup())
    elif text == "🔕 Тихо 1 час" and status == "admin":
        kv_set("muted_until", int(time.time()) + 3600)
        tg_send(cid, "🔕 Час тишины. 🔴 оповещения по нашему району всё равно придут.",
                reply_markup=MAIN_KB)

def handle_callback(cb):
    cid = cb["message"]["chat"]["id"]
    from_id = cb.get("from", {}).get("id")
    data = cb.get("data", "")
    status = user_status(from_id)
    if status not in ("admin", "approved"):
        tg_call("answerCallbackQuery", {"callback_query_id": cb["id"]})
        return

    if data.startswith(("appr:", "deny:")) and status == "admin":
        uid = int(data.split(":")[1])
        approve = data.startswith("appr:")
        with db_lock:
            row = db.execute("SELECT name, username FROM users WHERE id=?", (uid,)).fetchone()
        name, uname = row if row else ("", "")
        set_user_status(uid, "approved" if approve else "denied", name, uname)
        who = html.escape(name or str(uid)) + (f" (@{uname})" if uname else "")
        verdict = f"✅ <b>Одобрен:</b> {who}" if approve else f"❌ <b>Отклонён:</b> {who} — бот для него молчит"
        tg_call("editMessageText",
                {"chat_id": cid, "message_id": cb["message"]["message_id"],
                 "text": verdict, "parse_mode": "HTML"})
        if approve:
            tg_send(uid, WELCOME + "\n\n✅ Доступ открыт — теперь ты будешь "
                                   "получать оповещения.")
    elif data.startswith("tgl:") and status == "admin":
        k = data[4:]
        s = get_settings()
        set_setting(k, 0 if s.get(k) else 1)
        tg_call("editMessageReplyMarkup",
                {"chat_id": cid, "message_id": cb["message"]["message_id"],
                 "reply_markup": settings_markup()})
    elif data == "mute60":
        if status == "admin":
            kv_set("muted_until", int(time.time()) + 3600)
            tg_call("answerCallbackQuery", {"callback_query_id": cb["id"],
                                            "text": "🔕 Час тишины (кроме нашего района)"})
            return
    elif data == "ack":
        tg_call("editMessageReplyMarkup",
                {"chat_id": cid, "message_id": cb["message"]["message_id"],
                 "reply_markup": {"inline_keyboard": []}})
    elif data == "test" and status == "admin":
        alerts_q.put(("red", "uav", False,
                      f"ТЕСТ: {HOME_LABEL} — проверка оповещения. Это учебное сообщение.",
                      "тест", HOME_LABEL))
    tg_call("answerCallbackQuery", {"callback_query_id": cb["id"]})

def src_updates():
    offset = int(kv_get("upd_offset", "0"))
    while True:
        try:
            r = tg_call("getUpdates", {"offset": offset, "timeout": 45,
                                       "allowed_updates": ["message", "callback_query"]}, timeout=60)
            if not r or not r.get("ok"):
                time.sleep(5)
                continue
            for u in r["result"]:
                offset = max(offset, u["update_id"] + 1)
                kv_set("upd_offset", offset)
                try:
                    if "message" in u:
                        handle_message(u["message"])
                    elif "callback_query" in u:
                        handle_callback(u["callback_query"])
                except Exception:
                    log.exception("update handling")
        except Exception as e:
            log.warning("getUpdates: %s", e)
            time.sleep(5)

# ---------------------------------------------------------------- запуск

def main():
    log.info("=== БПЛА-Радар стартует (token: %s) ===", "есть" if TOKEN else "НЕТ — dry-run")
    threads = [
        threading.Thread(target=alert_worker, daemon=True, name="alerts"),
        threading.Thread(target=src_radar_russia, daemon=True, name="radar-russia"),
        threading.Thread(target=src_radar_map, daemon=True, name="radar-map"),
        threading.Thread(target=src_bplarussia, daemon=True, name="bplarussia"),
        threading.Thread(target=src_tme, daemon=True, name="tme"),
    ]
    if TOKEN:
        threads.append(threading.Thread(target=src_updates, daemon=True, name="updates"))
    for t in threads:
        t.start()
    if TOKEN:
        tg_send(ADMIN_ID, "🛡 <b>БПЛА-Радар запущен.</b> Слежу за небом над "
                          + html.escape(HOME_LABEL) + ".", reply_markup=MAIN_KB)
    while True:
        time.sleep(60)
        alive = {t.name: t.is_alive() for t in threads}
        dead = [n for n, a in alive.items() if not a]
        if dead:
            log.error("МЕРТВЫ ПОТОКИ: %s — выходим, PM2 перезапустит", dead)
            os._exit(1)

if __name__ == "__main__":
    main()
