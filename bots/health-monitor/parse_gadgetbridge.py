"""
Parse Gadgetbridge SQLite database to extract health metrics.
Supports Mi Band 10 (Xiaomi) via XIAOMI_* tables.
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
import config


def parse_db(db_path=None, target_date=None):
    """
    Parse Gadgetbridge DB and extract health data for a given date.
    If target_date is None, uses yesterday.
    """
    db_path = db_path or config.LOCAL_DB_PATH

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"DB not found: {db_path}")

    if target_date is None:
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        data = {
            "date": target_date,
            "report_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        tables = _get_tables(conn)

        # Timestamp range for target date
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        ts_start = int(dt.timestamp())
        ts_end = int((dt + timedelta(days=1)).timestamp())

        # Sleep window: previous evening 20:00 to target day 14:00
        sleep_ts_start = int((dt - timedelta(hours=4)).timestamp())
        sleep_ts_end = int((dt + timedelta(hours=14)).timestamp())

        # Parse activity data (heart rate, steps, SpO2, stress from minute samples)
        if "XIAOMI_ACTIVITY_SAMPLE" in tables:
            activity_data = _parse_xiaomi_activity(conn, ts_start, ts_end)
            sleep_activity = _parse_xiaomi_activity(conn, sleep_ts_start, sleep_ts_end)
            data["heart_rate_day"] = activity_data.get("heart_rate", {})
            data["activity"] = activity_data.get("steps", {})
            data["spo2"] = activity_data.get("spo2", {})
            data["stress"] = activity_data.get("stress", {})
        else:
            data["heart_rate_day"] = {"error": "no XIAOMI_ACTIVITY_SAMPLE table"}
            data["activity"] = {"error": "no activity data"}

        # Parse sleep from dedicated sleep tables
        if "XIAOMI_SLEEP_STAGE_SAMPLE" in tables:
            data["sleep"] = _parse_xiaomi_sleep(conn, sleep_ts_start, sleep_ts_end)
        elif "XIAOMI_ACTIVITY_SAMPLE" in tables:
            # Fallback: try to detect sleep from activity RAW_KIND
            data["sleep"] = _parse_sleep_from_activity(conn, sleep_ts_start, sleep_ts_end)
        else:
            data["sleep"] = {"error": "no sleep data"}

        # Enrich with daily summary if available
        if "XIAOMI_DAILY_SUMMARY_SAMPLE" in tables:
            summary = _parse_daily_summary(conn, target_date)
            if summary:
                data["daily_summary"] = summary
                # Fill in missing data from summary
                if data.get("spo2", {}).get("error") and summary.get("spo2_avg"):
                    data["spo2"] = {
                        "min": summary.get("spo2_min", 0),
                        "max": summary.get("spo2_max", 0),
                        "avg": summary.get("spo2_avg", 0),
                    }
                if data.get("stress", {}).get("error") and summary.get("stress_avg"):
                    data["stress"] = {
                        "avg": summary.get("stress_avg", 0),
                        "max": summary.get("stress_max", 0),
                        "min": summary.get("stress_min", 0),
                    }

        # Sleep time summary
        if "XIAOMI_SLEEP_TIME_SAMPLE" in tables:
            sleep_time = _parse_sleep_time(conn, sleep_ts_start, sleep_ts_end)
            if sleep_time and "sleep" in data and isinstance(data["sleep"], dict):
                data["sleep"].update(sleep_time)

        return data

    finally:
        conn.close()


def _get_tables(conn):
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [row[0] for row in cursor.fetchall()]


def _get_columns(conn, table):
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cursor.fetchall()]


def _parse_xiaomi_activity(conn, ts_start, ts_end):
    """Parse XIAOMI_ACTIVITY_SAMPLE for HR, steps, SpO2, stress."""
    query = """
        SELECT TIMESTAMP, STEPS, RAW_KIND, HEART_RATE, STRESS, SPO2,
               DISTANCE_CM, ACTIVE_CALORIES
        FROM XIAOMI_ACTIVITY_SAMPLE
        WHERE TIMESTAMP BETWEEN ? AND ?
        ORDER BY TIMESTAMP
    """
    rows = conn.execute(query, (ts_start, ts_end)).fetchall()

    result = {}

    # Heart rate
    hrs = [r["HEART_RATE"] for r in rows if r["HEART_RATE"] and 30 < r["HEART_RATE"] < 250]
    if hrs:
        hourly = defaultdict(list)
        for r in rows:
            if r["HEART_RATE"] and 30 < r["HEART_RATE"] < 250:
                hour = datetime.fromtimestamp(r["TIMESTAMP"]).hour
                hourly[hour].append(r["HEART_RATE"])

        sorted_hr = sorted(hrs)
        resting_count = max(1, len(sorted_hr) // 10)
        resting_hr = round(sum(sorted_hr[:resting_count]) / resting_count, 1)

        result["heart_rate"] = {
            "min": min(hrs),
            "max": max(hrs),
            "avg": round(sum(hrs) / len(hrs), 1),
            "resting": resting_hr,
            "readings_count": len(hrs),
            "hourly_avg": {
                f"{h:02d}:00": round(sum(v) / len(v), 1)
                for h, v in sorted(hourly.items())
            },
        }
    else:
        result["heart_rate"] = {"error": "no heart rate data"}

    # Steps
    total_steps = sum(r["STEPS"] for r in rows if r["STEPS"] and r["STEPS"] > 0)
    total_distance = sum(r["DISTANCE_CM"] for r in rows if r["DISTANCE_CM"] and r["DISTANCE_CM"] > 0)
    total_calories = sum(r["ACTIVE_CALORIES"] for r in rows if r["ACTIVE_CALORIES"] and r["ACTIVE_CALORIES"] > 0)

    hourly_steps = defaultdict(int)
    for r in rows:
        if r["STEPS"] and r["STEPS"] > 0:
            hour = datetime.fromtimestamp(r["TIMESTAMP"]).hour
            hourly_steps[hour] += r["STEPS"]

    result["steps"] = {
        "steps": total_steps,
        "distance_meters": total_distance // 100 if total_distance else int(total_steps * 0.72),
        "calories_active": total_calories,
        "hourly_steps": {f"{h:02d}:00": v for h, v in sorted(hourly_steps.items())} if hourly_steps else {},
    }

    # SpO2
    spo2_vals = [r["SPO2"] for r in rows if r["SPO2"] and 70 < r["SPO2"] <= 100]
    if spo2_vals:
        result["spo2"] = {
            "min": min(spo2_vals),
            "max": max(spo2_vals),
            "avg": round(sum(spo2_vals) / len(spo2_vals), 1),
            "readings_count": len(spo2_vals),
        }
    else:
        result["spo2"] = {"error": "no SpO2 data"}

    # Stress
    stress_vals = [r["STRESS"] for r in rows if r["STRESS"] and 0 < r["STRESS"] <= 100]
    if stress_vals:
        result["stress"] = {
            "avg": round(sum(stress_vals) / len(stress_vals), 1),
            "max": max(stress_vals),
            "min": min(stress_vals),
            "readings_count": len(stress_vals),
        }
    else:
        result["stress"] = {"error": "no stress data"}

    return result


def _parse_xiaomi_sleep(conn, ts_start, ts_end):
    """Parse sleep from XIAOMI_SLEEP_STAGE_SAMPLE."""
    STAGES = {0: "awake", 1: "light_sleep", 2: "deep_sleep", 3: "rem_sleep"}

    query = """
        SELECT TIMESTAMP, STAGE
        FROM XIAOMI_SLEEP_STAGE_SAMPLE
        WHERE TIMESTAMP BETWEEN ? AND ?
        ORDER BY TIMESTAMP
    """
    rows = conn.execute(query, (ts_start, ts_end)).fetchall()

    if not rows:
        return {"error": "no sleep stage data"}

    phases = []
    durations = {"deep_sleep": 0, "light_sleep": 0, "rem_sleep": 0, "awake": 0}

    for i, row in enumerate(rows):
        stage_name = STAGES.get(row["STAGE"], f"unknown_{row['STAGE']}")
        next_ts = rows[i + 1]["TIMESTAMP"] if i + 1 < len(rows) else row["TIMESTAMP"] + 60
        duration_min = (next_ts - row["TIMESTAMP"]) // 60

        if stage_name in durations:
            durations[stage_name] += duration_min

        phases.append({
            "phase": stage_name,
            "start": datetime.fromtimestamp(row["TIMESTAMP"]).strftime("%H:%M"),
            "duration_min": duration_min,
        })

    total = durations["deep_sleep"] + durations["light_sleep"] + durations["rem_sleep"]

    sleep_start = datetime.fromtimestamp(rows[0]["TIMESTAMP"]).strftime("%H:%M")
    sleep_end = datetime.fromtimestamp(rows[-1]["TIMESTAMP"]).strftime("%H:%M")

    # Get HR during sleep from activity table
    sleep_hr = _get_sleep_hr(conn, rows[0]["TIMESTAMP"], rows[-1]["TIMESTAMP"])

    result = {
        "start": sleep_start,
        "end": sleep_end,
        "total_minutes": total,
        "deep_minutes": durations["deep_sleep"],
        "light_minutes": durations["light_sleep"],
        "rem_minutes": durations["rem_sleep"],
        "awake_minutes": durations["awake"],
        "phases_detail": phases[:20],  # limit detail to avoid huge output
    }

    if sleep_hr:
        result["heart_rate_during_sleep"] = sleep_hr

    return result


def _parse_sleep_from_activity(conn, ts_start, ts_end):
    """Fallback: detect sleep from RAW_KIND in activity table."""
    SLEEP_KINDS = {2: "light_sleep", 3: "deep_sleep", 5: "rem_sleep", 6: "awake"}

    query = """
        SELECT TIMESTAMP, RAW_KIND, HEART_RATE
        FROM XIAOMI_ACTIVITY_SAMPLE
        WHERE TIMESTAMP BETWEEN ? AND ?
        AND RAW_KIND IN (2, 3, 5, 6)
        ORDER BY TIMESTAMP
    """
    rows = conn.execute(query, (ts_start, ts_end)).fetchall()

    if not rows:
        return {"error": "no sleep data detected from activity"}

    durations = {"deep_sleep": 0, "light_sleep": 0, "rem_sleep": 0, "awake": 0}
    sleep_hrs = []

    for i, row in enumerate(rows):
        kind = SLEEP_KINDS.get(row["RAW_KIND"], "unknown")
        if kind in durations:
            durations[kind] += 1  # each sample = ~1 minute

        if row["HEART_RATE"] and 30 < row["HEART_RATE"] < 200:
            sleep_hrs.append(row["HEART_RATE"])

    total = durations["deep_sleep"] + durations["light_sleep"] + durations["rem_sleep"]

    result = {
        "start": datetime.fromtimestamp(rows[0]["TIMESTAMP"]).strftime("%H:%M"),
        "end": datetime.fromtimestamp(rows[-1]["TIMESTAMP"]).strftime("%H:%M"),
        "total_minutes": total,
        "deep_minutes": durations["deep_sleep"],
        "light_minutes": durations["light_sleep"],
        "rem_minutes": durations["rem_sleep"],
        "awake_minutes": durations["awake"],
    }

    if sleep_hrs:
        result["heart_rate_during_sleep"] = {
            "min": min(sleep_hrs),
            "max": max(sleep_hrs),
            "avg": round(sum(sleep_hrs) / len(sleep_hrs), 1),
        }

    return result


def _get_sleep_hr(conn, ts_start, ts_end):
    """Get heart rate readings during sleep period."""
    query = """
        SELECT HEART_RATE FROM XIAOMI_ACTIVITY_SAMPLE
        WHERE TIMESTAMP BETWEEN ? AND ?
        AND HEART_RATE > 30 AND HEART_RATE < 200
    """
    rows = conn.execute(query, (ts_start, ts_end)).fetchall()
    if not rows:
        return None

    hrs = [r["HEART_RATE"] for r in rows]
    return {
        "min": min(hrs),
        "max": max(hrs),
        "avg": round(sum(hrs) / len(hrs), 1),
    }


def _parse_daily_summary(conn, target_date):
    """Parse XIAOMI_DAILY_SUMMARY_SAMPLE for aggregated daily data."""
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    # Xiaomi stores timestamp in milliseconds for daily summary
    ts_start_ms = int(dt.timestamp()) * 1000
    ts_end_ms = int((dt + timedelta(days=1)).timestamp()) * 1000

    # Also try seconds-based timestamps
    ts_start = int(dt.timestamp())
    ts_end = int((dt + timedelta(days=1)).timestamp())

    query = """
        SELECT * FROM XIAOMI_DAILY_SUMMARY_SAMPLE
        WHERE (TIMESTAMP BETWEEN ? AND ?) OR (TIMESTAMP BETWEEN ? AND ?)
        ORDER BY TIMESTAMP DESC LIMIT 1
    """
    rows = conn.execute(query, (ts_start_ms, ts_end_ms, ts_start, ts_end)).fetchall()

    if not rows:
        # Try getting the latest record
        rows = conn.execute(
            "SELECT * FROM XIAOMI_DAILY_SUMMARY_SAMPLE ORDER BY TIMESTAMP DESC LIMIT 1"
        ).fetchall()

    if not rows:
        return None

    r = rows[0]
    return {
        "steps": r["STEPS"],
        "hr_resting": r["HR_RESTING"],
        "hr_max": r["HR_MAX"],
        "hr_min": r["HR_MIN"],
        "hr_avg": r["HR_AVG"],
        "stress_avg": r["STRESS_AVG"],
        "stress_max": r["STRESS_MAX"],
        "stress_min": r["STRESS_MIN"],
        "spo2_max": r["SPO2_MAX"],
        "spo2_min": r["SPO2_MIN"],
        "spo2_avg": r["SPO2_AVG"],
        "calories": r["CALORIES"],
        "standing": r["STANDING"],
        "vitality_current": r["VITALITY_CURRENT"],
    }


def _parse_sleep_time(conn, ts_start, ts_end):
    """Parse XIAOMI_SLEEP_TIME_SAMPLE for sleep summary."""
    query = """
        SELECT * FROM XIAOMI_SLEEP_TIME_SAMPLE
        WHERE TIMESTAMP BETWEEN ? AND ?
        ORDER BY TIMESTAMP DESC LIMIT 1
    """
    rows = conn.execute(query, (ts_start, ts_end)).fetchall()

    if not rows:
        rows = conn.execute(
            "SELECT * FROM XIAOMI_SLEEP_TIME_SAMPLE ORDER BY TIMESTAMP DESC LIMIT 1"
        ).fetchall()

    if not rows:
        return None

    r = rows[0]
    result = {}
    if r["TOTAL_DURATION"]:
        result["total_minutes"] = r["TOTAL_DURATION"]
    if r["DEEP_SLEEP_DURATION"]:
        result["deep_minutes"] = r["DEEP_SLEEP_DURATION"]
    if r["LIGHT_SLEEP_DURATION"]:
        result["light_minutes"] = r["LIGHT_SLEEP_DURATION"]
    if r["REM_SLEEP_DURATION"]:
        result["rem_minutes"] = r["REM_SLEEP_DURATION"]
    if r["AWAKE_DURATION"]:
        result["awake_minutes"] = r["AWAKE_DURATION"]
    if r["WAKEUP_TIME"]:
        result["wakeup_time"] = datetime.fromtimestamp(r["WAKEUP_TIME"]).strftime("%H:%M")

    return result


def save_parsed_data(data):
    """Save parsed data to JSON file."""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    path = os.path.join(config.DATA_DIR, "health_data.json")
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Parsed data saved to {path}")
    return path
