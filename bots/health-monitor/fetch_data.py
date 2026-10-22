"""
Fetch Gadgetbridge SQLite DB from phone via SSH/SCP.
Also supports local file and demo mode.
"""

import os
import subprocess
import time
import config


GB_EXPORT_PATH = "/sdcard/Download/Gadgetbridge.db"
SYNC_INTENT = "nodomain.freeyourgadget.gadgetbridge.command.ACTIVITY_SYNC"
EXPORT_INTENT = "nodomain.freeyourgadget.gadgetbridge.command.TRIGGER_EXPORT"


def _ssh_cmd(command, timeout=15):
    """Run a command on phone via SSH."""
    cmd = ["ssh", config.PHONE_SSH_HOST, "-o", "ConnectTimeout=5", command]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "timeout"


def fetch_from_phone():
    """Trigger sync + export on phone, then SCP the DB."""
    os.makedirs(config.DATA_DIR, exist_ok=True)

    # Step 1: Trigger activity sync
    print("Triggering activity sync on phone...")
    ok, out = _ssh_cmd(f'am broadcast -a "{SYNC_INTENT}"')
    if ok:
        print("Sync triggered, waiting 20s for data...")
        time.sleep(20)
    else:
        print(f"Sync trigger failed: {out}")

    # Step 2: Trigger DB export
    print("Triggering DB export...")
    ok, out = _ssh_cmd(f'am broadcast -a "{EXPORT_INTENT}"')
    if ok:
        print("Export triggered, waiting 5s...")
        time.sleep(5)
    else:
        print(f"Export trigger failed: {out}")

    # Step 3: SCP the exported DB
    print("Fetching DB via SCP...")
    cmd = [
        "scp",
        "-o", "ConnectTimeout=10",
        f"{config.PHONE_SSH_HOST}:{GB_EXPORT_PATH}",
        config.LOCAL_DB_PATH
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            size = os.path.getsize(config.LOCAL_DB_PATH)
            print(f"DB fetched: {config.LOCAL_DB_PATH} ({size} bytes)")
            return config.LOCAL_DB_PATH
        else:
            print(f"SCP failed: {result.stderr}")
            return None
    except subprocess.TimeoutExpired:
        print("SCP timeout - phone not reachable")
        return None


def fetch_from_local(path=None):
    """Use a local Gadgetbridge DB file."""
    path = path or config.LOCAL_DB_PATH
    if os.path.exists(path):
        return path
    print(f"Local DB not found: {path}")
    return None


def generate_demo_data():
    """Generate realistic demo data for testing without a real device."""
    import json
    import random
    from datetime import datetime, timedelta

    now = datetime.now()
    yesterday = now - timedelta(days=1)

    sleep_start = yesterday.replace(hour=23, minute=random.randint(0, 45))
    sleep_end = now.replace(hour=random.randint(6, 8), minute=random.randint(0, 59))
    total_sleep_min = int((sleep_end - sleep_start).total_seconds() / 60)
    deep_sleep = int(total_sleep_min * random.uniform(0.15, 0.25))
    rem_sleep = int(total_sleep_min * random.uniform(0.18, 0.25))
    light_sleep = total_sleep_min - deep_sleep - rem_sleep - random.randint(5, 20)
    awake = total_sleep_min - deep_sleep - rem_sleep - light_sleep

    sleep_hr = []
    for i in range(total_sleep_min):
        phase_progress = i / total_sleep_min
        if phase_progress < 0.3:
            hr = random.randint(58, 68)
        elif phase_progress < 0.6:
            hr = random.randint(48, 58)
        elif phase_progress < 0.85:
            hr = random.randint(55, 72)
        else:
            hr = random.randint(62, 78)
        sleep_hr.append(hr)

    spo2_readings = [random.randint(94, 99) for _ in range(0, total_sleep_min, 30)]
    total_steps = random.randint(5000, 12000)

    stress_readings = [{"hour": h, "level": random.randint(20, 75)} for h in range(8, 23)]

    data = {
        "date": yesterday.strftime("%Y-%m-%d"),
        "report_time": now.strftime("%Y-%m-%d %H:%M"),
        "sleep": {
            "start": sleep_start.strftime("%H:%M"),
            "total_minutes": total_sleep_min,
            "deep_minutes": deep_sleep,
            "light_minutes": light_sleep,
            "rem_minutes": rem_sleep,
            "awake_minutes": awake,
            "heart_rate_during_sleep": {
                "min": min(sleep_hr), "max": max(sleep_hr),
                "avg": round(sum(sleep_hr) / len(sleep_hr), 1),
            },
        },
        "activity": {
            "steps": total_steps,
            "distance_meters": int(total_steps * 0.72),
            "calories_active": int(total_steps * 0.04),
        },
        "heart_rate_day": {
            "min": min(sleep_hr), "max": max(sleep_hr) + 40,
            "avg": round(sum(sleep_hr) / len(sleep_hr) + 10, 1),
            "resting": min(sleep_hr),
        },
        "spo2": {
            "min": min(spo2_readings), "max": max(spo2_readings),
            "avg": round(sum(spo2_readings) / len(spo2_readings), 1),
        },
        "stress": {
            "avg": round(sum(s["level"] for s in stress_readings) / len(stress_readings), 1),
            "max": max(s["level"] for s in stress_readings),
        },
    }

    os.makedirs(config.DATA_DIR, exist_ok=True)
    path = os.path.join(config.DATA_DIR, "health_data.json")
    with open(path, "w") as f:
        import json as j
        j.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Demo data generated: {path}")
    return data
