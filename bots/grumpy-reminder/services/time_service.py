from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import APP_TIMEZONE, HUMAN_DATETIME_FORMAT, UTC


@dataclass
class NormalizedDateTime:
    local: datetime
    storage_iso: str
    human: str


def parse_user_datetime(raw: str, tz: ZoneInfo) -> datetime:
    """
    Convert string from AI (local naive or aware) to timezone-aware local datetime.
    """
    clean = raw.strip()
    if clean.endswith("Z"):
        clean = clean[:-1] + "+00:00"

    dt = datetime.fromisoformat(clean)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    else:
        dt = dt.astimezone(tz)

    return dt


def normalize_datetime(raw: str, tz: ZoneInfo) -> NormalizedDateTime:
    local_dt = parse_user_datetime(raw, tz)
    storage_iso = local_dt.astimezone(UTC).isoformat()
    human = local_dt.strftime(HUMAN_DATETIME_FORMAT)
    return NormalizedDateTime(local=local_dt, storage_iso=storage_iso, human=human)


def storage_to_local(storage_iso: str, tz: ZoneInfo) -> NormalizedDateTime:
    clean = storage_iso.strip()
    if clean.endswith("Z"):
        clean = clean[:-1] + "+00:00"
    dt = datetime.fromisoformat(clean)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    local_dt = dt.astimezone(tz)
    return NormalizedDateTime(
        local=local_dt,
        storage_iso=dt.astimezone(UTC).isoformat(),
        human=local_dt.strftime(HUMAN_DATETIME_FORMAT),
    )


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def resolve_timezone(name: Optional[str]) -> ZoneInfo:
    if not name:
        return APP_TIMEZONE
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return APP_TIMEZONE
