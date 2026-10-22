from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

import pytz
from geopy import geocoders
from geopy.exc import GeocoderServiceError, GeopyError
from timezonefinder import TimezoneFinder
from unidecode import unidecode

from config import logger


CITY_MAPPING = {
    "moscow": "Europe/Moscow",
    "moskva": "Europe/Moscow",
    "moskwa": "Europe/Moscow",
    "saint petersburg": "Europe/Moscow",
    "sankt peterburg": "Europe/Moscow",
    "sankt-peterburg": "Europe/Moscow",
    "st petersburg": "Europe/Moscow",
    "ekaterinburg": "Asia/Yekaterinburg",
    "yekaterinburg": "Asia/Yekaterinburg",
    "novosibirsk": "Asia/Novosibirsk",
    "krasnoyarsk": "Asia/Krasnoyarsk",
    "irkutsk": "Asia/Irkutsk",
    "yakutsk": "Asia/Yakutsk",
    "blagoveshchensk": "Asia/Yakutsk",
    "blagoveschensk": "Asia/Yakutsk",
    "habarovsk": "Asia/Vladivostok",
    "khabarovsk": "Asia/Vladivostok",
    "vladivostok": "Asia/Vladivostok",
    "magadan": "Asia/Magadan",
    "kamchatka": "Asia/Kamchatka",
    "new york": "America/New_York",
    "los angeles": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "chicago": "America/Chicago",
    "london": "Europe/London",
    "berlin": "Europe/Berlin",
    "paris": "Europe/Paris",
    "tokyo": "Asia/Tokyo",
    "seoul": "Asia/Seoul",
    "beijing": "Asia/Shanghai",
    "shanghai": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong",
    "singapore": "Asia/Singapore",
}


class TimezoneResolver:
    def __init__(self) -> None:
        self._tf = TimezoneFinder()
        self._geolocator = geocoders.Nominatim(user_agent="aggressive-reminder-bot", timeout=5)

    @lru_cache(maxsize=256)
    def resolve(self, query: str) -> Optional[str]:
        if not query:
            return None

        cleaned = query.strip()

        tz = self._geocode_timezone(cleaned)
        if tz:
            return tz

        tz = self._fuzzy_timezone(cleaned)
        if tz:
            return tz

        return None

    def _geocode_timezone(self, query: str) -> Optional[str]:
        try:
            location = self._geolocator.geocode(query, language="ru,en", addressdetails=True)
            if not location:
                return None

            timezone = self._tf.timezone_at(lng=location.longitude, lat=location.latitude)
            return timezone
        except (GeopyError, GeocoderServiceError) as exc:
            logger.warning("Geocoding timezone failed for %s: %s", query, exc)
            return None

    def _fuzzy_timezone(self, query: str) -> Optional[str]:
        normalized_query = self._normalize(query)

        if normalized_query in CITY_MAPPING:
            return CITY_MAPPING[normalized_query]

        best_match = None
        best_score = 0

        for tz in pytz.all_timezones:
            normalized_tz = self._normalize(tz)
            score = self._match_score(normalized_query, normalized_tz)
            if score > best_score:
                best_score = score
                best_match = tz

        if best_score >= 0.8:
            return best_match
        return None

    @staticmethod
    def _normalize(text: str) -> str:
        text_ascii = unidecode(text.lower())
        text_ascii = text_ascii.replace('-', ' ').replace('_', ' ')
        text_ascii = re.sub(r"[^a-z0-9/ ]", "", text_ascii)
        return re.sub(r"\s+", " ", text_ascii).strip()

    @staticmethod
    def _match_score(a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        if a in b:
            return len(a) / len(b)
        return 0.0


timezone_resolver = TimezoneResolver()


def fallback_timezone(query: str) -> Optional[str]:
    return timezone_resolver.resolve(query)
