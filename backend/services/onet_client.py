"""O*NET Web Services API client.

Authenticates with HTTP Basic Auth: ONET_API_KEY as username, "nologin" as
password.  Set the ONET_API_KEY environment variable before instantiating
OnetClient (see .env.example).

API reference: https://services.onetcenter.org/developer/
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import requests
from requests.auth import HTTPBasicAuth

_BASE_URL = "https://services.onetcenter.org/ws"
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
    """Thin wrapper around the O*NET Web Services v1.9 REST API.

    Args:
        api_key: Overrides the ONET_API_KEY environment variable when provided.

    Raises:
        ValueError: When no API key is available.
    """

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.environ.get("ONET_API_KEY")
        if not key:
            raise ValueError(
                "ONET_API_KEY is not set. "
                "Add it to your environment or pass api_key= directly."
            )
        self._session = requests.Session()
        self._session.auth = HTTPBasicAuth(key, "nologin")
        self._session.headers.update({"Accept": "application/json"})

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
        """Return skills for *onet_code* with importance and level scores.

        Args:
            onet_code: O*NET-SOC code such as ``"15-1252.00"``.

        Returns:
            List of skills.  Missing importance or level defaults to ``0.0``.

        Example response key accessed: ``data["element"]``
        Each element: ``{"id": "2.A.1.a", "name": "...",
                         "score": {"importance": {"value": 72.0},
                                   "level":      {"value": 4.25}}}``
        """
        data = self._get(f"online/occupations/{onet_code}/summary/skills")
        skills: list[Skill] = []
        for element in data.get("element", []):
            score = element.get("score", {})
            skills.append(
                Skill(
                    element_id=element["id"],
                    name=element["name"],
                    importance=float(
                        score.get("importance", {}).get("value", 0.0)
                    ),
                    level=float(
                        score.get("level", {}).get("value", 0.0)
                    ),
                )
            )
        return skills

    def get_job_zone(self, onet_code: str) -> int:
        """Return the Job Zone (1–5) for *onet_code*.

        Args:
            onet_code: O*NET-SOC code such as ``"15-1252.00"``.

        Returns:
            Integer job zone between 1 and 5.

        Example response key accessed: ``data["job_zone"]["value"]``
        """
        data = self._get(f"online/occupations/{onet_code}/summary/job_zone")
        return int(data["job_zone"]["value"])
