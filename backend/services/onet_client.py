"""O*NET Web Services v2 API client.

Authenticates via X-API-Key header.  Set the ONET_API_KEY environment variable
before instantiating OnetClient (see .env.example).

API reference: https://api-v2.onetcenter.org/
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import requests

_log = logging.getLogger(__name__)

_BASE_URL = "https://api-v2.onetcenter.org"
_TIMEOUT = 10  # seconds
_MAX_RETRIES = 3
# O*NET recommends waiting ≥200 ms before retrying after a 429.
_RETRY_DELAY = 0.25  # seconds; multiplied by attempt number


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
        """
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

        return [
            Skill(
                element_id=e.get("id", ""),
                name=e.get("name", ""),
                importance=float(e.get("importance", 0.0)),
                level=0.0,
            )
            for e in elements
        ]

    def get_tech_skills(self, onet_code: str, hot_only: bool = False) -> set[str]:
        """Return a lowercase set of technology tool names for *onet_code*.

        Uses /details/technology_skills which lists specific software, tools,
        and platforms (e.g. "Python", "React", "TypeScript") — compatible with
        user profile skill tags.  Same .00→.01 fallback as get_skills_profile.

        Args:
            hot_only: When True, returns only tools flagged as hot technologies
                      by O*NET (trending, in-demand tools). Typically 10–20 per
                      role vs. 200+ for the full list.
        """
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
        return names

    def get_job_zone(self, onet_code: str) -> int:
        """Return the Job Zone (1–5) for *onet_code*.

        Args:
            onet_code: O*NET-SOC code such as ``"15-1252.00"``.

        Returns:
            Integer job zone between 1 and 5.
        """
        data = self._get(f"online/occupations/{onet_code}/summary/job_zone")
        # v2 response: {"code": 4, "title": "Job Zone Four: ..."}
        return int(data["code"])
