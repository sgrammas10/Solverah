"""O*NET Web Services v2 API client.

Authenticates via X-API-Key header.  Set the ONET_API_KEY environment variable
before instantiating OnetClient (see .env.example).

API reference: https://api-v2.onetcenter.org/
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass

import requests

_log = logging.getLogger(__name__)

_BASE_URL = "https://api-v2.onetcenter.org"

# Module-level cache for Bright Outlook occupations — same list for every user,
# changes only quarterly, so 24-hour TTL avoids hammering the API.
_BRIGHT_OUTLOOK_CACHE: list["Occupation"] = []
_BRIGHT_OUTLOOK_CACHE_TS: float = 0.0
_BRIGHT_OUTLOOK_CACHE_TTL: float = 86400.0  # 24 hours
_TIMEOUT = 10  # seconds
_MAX_RETRIES = 3
# O*NET recommends waiting ≥200 ms before retrying after a 429.
_RETRY_DELAY = 0.25  # seconds; multiplied by attempt number

# Occupation-level cache for get_job_zone / get_skills_profile / get_tech_skills /
# get_work_activities.  Keyed by (method_name, onet_code, extra_params) so e.g.
# hot_only=True/False variants of get_tech_skills don't collide.  This data is
# per-occupation, not per-user, and shared across every per-request OnetClient()
# instance since it's module scope (same property _BRIGHT_OUTLOOK_CACHE already
# relies on) — O*NET content changes only quarterly, so a 24h TTL is safe.
_OCC_CACHE: dict[tuple, tuple[float, object]] = {}
_OCC_CACHE_TTL: float = 86400.0  # 24 hours
# Guards only the dict read/write, never the network call itself — holding a
# lock across a blocking HTTP request would serialize every candidate fetch
# and defeat the point of fetching candidates concurrently.  A cold cache can
# therefore see a handful of duplicate live fetches from racing threads on the
# very first request for a given code; this is a deliberate, self-healing
# tradeoff, not a bug.
_OCC_CACHE_LOCK = threading.Lock()


def _occ_cache_get(key: tuple) -> object | None:
    """Return a cached value for *key* if present and unexpired, else None.

    Callers must treat the returned value as immutable — list/set results are
    shared across every caller hitting the cache, so onet_client itself makes
    a shallow copy before handing a cached value back (see call sites below).
    """
    with _OCC_CACHE_LOCK:
        entry = _OCC_CACHE.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.monotonic() - ts >= _OCC_CACHE_TTL:
        return None
    return value


def _occ_cache_set(key: tuple, value: object) -> None:
    """Store *value* in the cache.

    Stores a shallow copy of list/set values, not *value* itself — the caller
    that just fetched it also returns that same object to its own caller, and
    without copying here, a mutation of that first return value would corrupt
    every subsequent cache hit for this key.
    """
    if isinstance(value, list):
        value = list(value)
    elif isinstance(value, set):
        value = set(value)
    with _OCC_CACHE_LOCK:
        _OCC_CACHE[key] = (time.monotonic(), value)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Occupation:
    code: str   # O*NET-SOC code, e.g. "15-1252.00"
    title: str


@dataclass
class Skill:
    element_id: str   # O*NET element ID, e.g. "2.A.1.a"
    name: str
    importance: float  # IM scale: 0–100
    level: float       # LV scale: 0–7


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class OnetRateLimitError(Exception):
    """HTTP 429 received from the O*NET API and all retries were exhausted."""


class OnetAPIError(Exception):
    """Non-recoverable HTTP error from the O*NET API."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class OnetClient:
    """Thin wrapper around the O*NET Web Services v2 REST API."""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.environ.get("ONET_API_KEY")
        if not key:
            raise ValueError(
                "ONET_API_KEY is not set. "
                "Add it to your environment or pass api_key= directly."
            )
        self._session = requests.Session()
        self._session.headers.update({
            "X-API-Key": key,
            "Accept": "application/json",
        })

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(
        self,
        path: str,
        params: dict[str, str | int] | None = None,
    ) -> dict:
        """GET *path* relative to the base URL with automatic 429 retry."""
        url = f"{_BASE_URL}/{path.lstrip('/')}"
        for attempt in range(_MAX_RETRIES):
            resp = self._session.get(url, params=params, timeout=_TIMEOUT)
            if resp.status_code == 429:
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_DELAY * (attempt + 1))
                    continue
                raise OnetRateLimitError(
                    f"O*NET rate limit hit after {_MAX_RETRIES} attempts on {url}"
                )
            try:
                resp.raise_for_status()
            except requests.HTTPError as exc:
                raise OnetAPIError(str(exc)) from exc
            return resp.json()
        # Unreachable — satisfies type checker.
        raise OnetRateLimitError("Rate limit exhausted")  # pragma: no cover

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search_occupations(self, title: str) -> list[Occupation]:
        """Search O*NET for occupations matching *title*.

        Args:
            title: Free-text job title to search for.

        Returns:
            List of matching occupations (up to 20 by default).

        Example response key accessed: ``data["occupation"]``
        """
        data = self._get("online/search", params={"keyword": title})
        return [
            Occupation(code=occ["code"], title=occ["title"])
            for occ in data.get("occupation", [])
        ]

    def get_skills_profile(self, onet_code: str) -> list[Skill]:
        """Return skills for *onet_code* sorted by importance descending.

        v2 endpoint: /details/skills — each element has a flat ``importance``
        integer (0–100).  No level (LV) scale is exposed at this endpoint.
        Requests up to 100 elements to cover all skills in one call.

        .00 codes are O*NET umbrella occupations whose skills data lives in
        the .01 sub-code; falls back automatically when the parent is empty.

        Result is cached per onet_code for _OCC_CACHE_TTL seconds (24h) — skills
        are per-occupation, not per-user, and O*NET content changes quarterly.
        """
        cache_key = ("get_skills_profile", onet_code, ())
        cached = _occ_cache_get(cache_key)
        if cached is not None:
            return list(cached)

        def _fetch(code: str) -> list[dict]:
            data = self._get(
                f"online/occupations/{code}/details/skills",
                params={"end": 100},
            )
            return data.get("element") or []

        elements = _fetch(onet_code)
        if not elements and onet_code.endswith(".00"):
            fallback = onet_code[:-3] + ".01"
            _log.debug("skills empty for %s, trying sub-code %s", onet_code, fallback)
            elements = _fetch(fallback)
        if not elements:
            _log.warning("skills empty for %s (no fallback data)", onet_code)

        result = [
            Skill(
                element_id=e.get("id", ""),
                name=e.get("name", ""),
                importance=float(e.get("importance", 0.0)),
                level=0.0,
            )
            for e in elements
        ]
        _occ_cache_set(cache_key, result)
        return result

    def get_tech_skills(self, onet_code: str, hot_only: bool = False) -> set[str]:
        """Return a lowercase set of technology tool names for *onet_code*.

        Uses /details/technology_skills which lists specific software, tools,
        and platforms (e.g. "Python", "React", "TypeScript") — compatible with
        user profile skill tags.  Same .00→.01 fallback as get_skills_profile.

        Args:
            hot_only: When True, returns only tools flagged as hot technologies
                      by O*NET (trending, in-demand tools). Typically 10–20 per
                      role vs. 200+ for the full list.

        Result is cached per (onet_code, hot_only) for _OCC_CACHE_TTL seconds
        (24h) — hot_only is part of the cache key since it changes the result.
        """
        cache_key = ("get_tech_skills", onet_code, (hot_only,))
        cached = _occ_cache_get(cache_key)
        if cached is not None:
            return set(cached)

        def _fetch(code: str) -> set[str]:
            data = self._get(
                f"online/occupations/{code}/details/technology_skills",
                params={"end": 100},
            )
            names: set[str] = set()
            for cat in data.get("category", []):
                for ex in cat.get("example", []):
                    if not hot_only or ex.get("hot_technology", False):
                        names.add(ex["title"].lower())
                for ex in cat.get("example_more", []):
                    if not hot_only or ex.get("hot_technology", False):
                        names.add(ex["title"].lower())
            return names

        names = _fetch(onet_code)
        if not names and onet_code.endswith(".00"):
            fallback = onet_code[:-3] + ".01"
            _log.debug("tech skills empty for %s, trying sub-code %s", onet_code, fallback)
            names = _fetch(fallback)
        if not names:
            _log.warning("tech skills empty for %s (no fallback data)", onet_code)
        _occ_cache_set(cache_key, names)
        return names

    def get_work_activities(self, onet_code: str) -> list[Skill]:
        """Return work activities for *onet_code* sorted by importance descending.

        Hits the /details/work_activities endpoint.  Same .00→.01 fallback as
        get_skills_profile.  Returns Skill objects (element_id, name, importance).

        Result is cached per onet_code for _OCC_CACHE_TTL seconds (24h) — same
        rationale as get_skills_profile.
        """
        cache_key = ("get_work_activities", onet_code, ())
        cached = _occ_cache_get(cache_key)
        if cached is not None:
            return list(cached)

        def _fetch(code: str) -> list[dict]:
            data = self._get(
                f"online/occupations/{code}/details/work_activities",
                params={"end": 100},
            )
            return data.get("element") or []

        elements = _fetch(onet_code)
        if not elements and onet_code.endswith(".00"):
            fallback = onet_code[:-3] + ".01"
            _log.debug("work activities empty for %s, trying sub-code %s", onet_code, fallback)
            elements = _fetch(fallback)

        result = [
            Skill(
                element_id=e.get("id", ""),
                name=e.get("name", ""),
                importance=float(e.get("importance", 0.0)),
                level=0.0,
            )
            for e in elements
        ]
        _occ_cache_set(cache_key, result)
        return result

    def get_bright_outlook_occupations(self) -> list[Occupation]:
        """Return all Bright Outlook occupations, deduplicated across the three categories.

        Fetches /online/bright_outlook/ for category codes, then each category's
        occupations from /online/bright_outlook/[category_code].  Results are cached
        for _BRIGHT_OUTLOOK_CACHE_TTL seconds (24h) — the list changes only quarterly.
        On any OnetAPIError returns the stale cache (possibly empty) so the caller
        can fall back to profile-seeded search.
        """
        global _BRIGHT_OUTLOOK_CACHE, _BRIGHT_OUTLOOK_CACHE_TS
        now = time.monotonic()
        if _BRIGHT_OUTLOOK_CACHE and now - _BRIGHT_OUTLOOK_CACHE_TS < _BRIGHT_OUTLOOK_CACHE_TTL:
            return _BRIGHT_OUTLOOK_CACHE
        try:
            data = self._get("online/bright_outlook")
            categories = [cat["code"] for cat in data.get("bright_outlook_category", [])]
            seen: set[str] = set()
            result: list[Occupation] = []
            for category_code in categories:
                cat_data = self._get(f"online/bright_outlook/{category_code}")
                for occ_data in cat_data.get("occupation", []):
                    code = occ_data.get("code", "")
                    if code and code not in seen:
                        seen.add(code)
                        result.append(Occupation(code=code, title=occ_data.get("title", "")))
            _BRIGHT_OUTLOOK_CACHE = result
            _BRIGHT_OUTLOOK_CACHE_TS = now
            return result
        except OnetAPIError:
            _log.warning("get_bright_outlook_occupations failed; returning stale cache", exc_info=True)
            return _BRIGHT_OUTLOOK_CACHE

    def get_job_families(self) -> list[dict]:
        """Return all SOC job family codes and titles from /online/job_families/.

        Each dict has "code" (e.g. "15-0000") and "title" keys.
        Raises OnetAPIError on failure.
        """
        data = self._get("online/job_families")
        return [
            {"code": fam.get("code", ""), "title": fam.get("title", "")}
            for fam in data.get("job_family", [])
        ]

    def get_job_family_occupations(self, family_code: str) -> list[Occupation]:
        """Return all occupations within a SOC job family.

        Requests up to 100 entries to cover the full family in one call — the
        largest O*NET family (15-0000) has ~38 occupations as of 2024.

        Args:
            family_code: SOC major-group code, e.g. "15-0000".

        Raises:
            OnetAPIError: On any HTTP error.
        """
        data = self._get(f"online/job_families/{family_code}", params={"end": 100})
        return [
            Occupation(code=occ_data.get("code", ""), title=occ_data.get("title", ""))
            for occ_data in data.get("occupation", [])
        ]

    def get_job_zone(self, onet_code: str) -> int:
        """Return the Job Zone (1–5) for *onet_code*.

        Args:
            onet_code: O*NET-SOC code such as ``"15-1252.00"``.

        Returns:
            Integer job zone between 1 and 5.

        Result is cached per onet_code for _OCC_CACHE_TTL seconds (24h) — same
        rationale as get_skills_profile.
        """
        cache_key = ("get_job_zone", onet_code, ())
        cached = _occ_cache_get(cache_key)
        if cached is not None:
            return cached

        data = self._get(f"online/occupations/{onet_code}/summary/job_zone")
        # v2 response: {"code": 4, "title": "Job Zone Four: ..."}
        zone = int(data["code"])
        _occ_cache_set(cache_key, zone)
        return zone
