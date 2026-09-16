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
#
# Audited 2026-09-16 alongside the _OCC_CACHE fix below and found NOT to leak, so
# deliberately left alone: this is one list rebuilt and rebound wholesale on
# refresh, never appended to and never keyed, so it cannot accumulate.  Its size
# is bounded by construction at three categories x end=100, deduplicated —
# at most ~300 Occupation records, roughly 60 KB.  The stale-cache return on
# OnetAPIError is a fallback path, not a growth path.
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

#: Hard ceiling on cached occupation records per worker.
#:
#: Added 2026-09-16 after the production OOM: before it, this cache had no size
#: bound of any kind, and its TTL was consulted only on read, so an entry nobody
#: asked for again was never evaluated and never removed — a leak wearing a
#: TTL's clothing, the same shape agent_service._evict_expired_locked names and
#: fixes for itself.  The TTL is the mechanism; this is the backstop for the case
#: where every entry is genuinely live at once.
#:
#: 2,048 entries is measured, not guessed.  Entries cost ~6.0 KB on average
#: (measured 2026-09-16: 9.38 KB for a 35-element skills profile, 10.85 KB for a
#: 41-element work-activity list, 3.71 KB for a hot-tech name set, 0.09 KB for a
#: job zone), so the cap is ~11.4 MB.  gunicorn.conf.py runs `workers = 1` on a
#: 512 MB Render Starter, so that is one copy, not three — 2.2% of the dyno.
#:
#: Four methods cache per occupation, so 2,048 entries is ~512 fully-cached
#: occupations, about half of O*NET.  One scoring run touches 30–80 occupations
#: (120–320 entries), so this retains ~6–17 runs — deliberately the same
#: retention depth as path_scoring._EMBED_CACHE's byte budget, since the two
#: caches are filled by the same requests and a cap that evicted one but not the
#: other would just move the miss.
_OCC_CACHE_MAX_ENTRIES: int = int(
    os.environ.get("SOLVERAH_OCC_CACHE_MAX_ENTRIES", 2048)
)
# Guards only the dict read/write, never the network call itself — holding a
# lock across a blocking HTTP request would serialize every candidate fetch
# and defeat the point of fetching candidates concurrently.  A cold cache can
# therefore see a handful of duplicate live fetches from racing threads on the
# very first request for a given code; this is a deliberate, self-healing
# tradeoff, not a bug.
_OCC_CACHE_LOCK = threading.Lock()


def _sweep_expired_locked(now: float) -> None:
    """Drop every entry whose TTL has passed.  Caller must hold the lock.

    Sweeping on write is what makes the TTL real.  Checking it only on read --
    the behaviour before 2026-09-16 -- means an entry nobody reads again is
    never evaluated and so never removed.  Same reasoning, and deliberately the
    same shape, as solverah/services/agent_service.py's _evict_expired_locked.
    """
    for key in [k for k, (ts, _) in _OCC_CACHE.items() if now - ts >= _OCC_CACHE_TTL]:
        del _OCC_CACHE[key]


def _evict_oldest_locked() -> None:
    """Trim the cache to _OCC_CACHE_MAX_ENTRIES, oldest-inserted first.

    Caller must hold the lock.  next(iter(...)) rather than dict.popitem(), which
    pops the *newest* entry -- the wrong end.  dicts preserve insertion order, so
    the first key is the oldest, and re-setting an existing key does not move it.
    """
    while len(_OCC_CACHE) > _OCC_CACHE_MAX_ENTRIES:
        del _OCC_CACHE[next(iter(_OCC_CACHE))]


def _occ_cache_get(key: tuple) -> object | None:
    """Return a cached value for *key* if present and unexpired, else None.

    Deletes the entry when it has expired, rather than merely declining to
    return it: leaving it resident is what turned a 24-hour TTL into unbounded
    growth before 2026-09-16.

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
            # pop, not del: a racing thread may already have swept this key.
            _OCC_CACHE.pop(key, None)
            return None
        return value


def _occ_cache_set(key: tuple, value: object) -> None:
    """Store *value* in the cache, sweeping expired entries and capping size.

    Stores a shallow copy of list/set values, not *value* itself — the caller
    that just fetched it also returns that same object to its own caller, and
    without copying here, a mutation of that first return value would corrupt
    every subsequent cache hit for this key.
    """
    if isinstance(value, list):
        value = list(value)
    elif isinstance(value, set):
        value = set(value)
    now = time.monotonic()
    with _OCC_CACHE_LOCK:
        _sweep_expired_locked(now)
        _OCC_CACHE[key] = (now, value)
        _evict_oldest_locked()


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


@dataclass
class Task:
    """One occupational task statement from /details/tasks.

    ``importance`` is the IM scale (0–100) and ``category`` is O*NET's own
    "Core"/"Supplemental" split — both are absent from the cheaper
    /summary/tasks endpoint, which is why this client uses /details.  They cost
    the same single request and let a caller rank and trim the task list
    instead of taking whatever order the API returned.
    """

    task_id: str
    title: str
    importance: float
    category: str


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

    def get_occupation_description(self, onet_code: str) -> str:
        """Return O*NET's description paragraph for *onet_code*.

        Hits the occupation root, ``/online/occupations/[code]``, whose payload
        carries ``title``, ``description`` and a table of links to every
        sub-resource.  One request, ~2–4 sentences of concrete prose -- the
        half of a role document that says what the job *is*, as opposed to
        ``get_tasks`` which says what the job *does*.

        Returns an empty string when the field is absent rather than raising:
        a missing description degrades a role document, it does not invalidate
        it, and the corpus builder must not lose an occupation over one blank
        field.

        No .00 -> .01 fallback, unlike get_skills_profile and friends.  Every
        occupation the catalog enumerates has its own description, including
        umbrella .00 codes whose *ratings* live in the sub-codes -- verified
        against the live v2 API 2026-09-16.

        Result is cached per onet_code for _OCC_CACHE_TTL seconds (24h), same
        rationale as get_skills_profile.
        """
        cache_key = ("get_occupation_description", onet_code, ())
        cached = _occ_cache_get(cache_key)
        if cached is not None:
            return str(cached)

        data = self._get(f"online/occupations/{onet_code}")
        description = str(data.get("description") or "")
        if not description:
            _log.warning("description empty for %s", onet_code)
        _occ_cache_set(cache_key, description)
        return description

    def get_tasks(self, onet_code: str) -> list[Task]:
        """Return task statements for *onet_code*, most important first.

        v2 endpoint: ``/details/tasks`` -- each entry has ``id``, ``title``,
        ``importance`` (0-100) and ``category`` ("Core"/"Supplemental").  The
        cheaper ``/summary/tasks`` returns the same statements without those
        last two fields, so it costs one request either way and gives the
        caller nothing to rank by; this client takes the richer one.

        Sorted by importance descending here rather than at the call site so
        that "top N tasks" means the same thing everywhere.  O*NET already
        returns them in that order, but that is its choice, not a contract.

        Same .00 -> .01 fallback as get_skills_profile: an umbrella code with
        no task data of its own borrows its first sub-code's.

        Requests up to 100 entries in one call -- the largest task list in the
        catalog is well under that.

        Result is cached per onet_code for _OCC_CACHE_TTL seconds (24h).
        """
        cache_key = ("get_tasks", onet_code, ())
        cached = _occ_cache_get(cache_key)
        if cached is not None:
            return list(cached)

        def _fetch(code: str) -> list[dict]:
            data = self._get(
                f"online/occupations/{code}/details/tasks",
                params={"end": 100},
            )
            return data.get("task") or []

        entries = _fetch(onet_code)
        if not entries and onet_code.endswith(".00"):
            fallback = onet_code[:-3] + ".01"
            _log.debug("tasks empty for %s, trying sub-code %s", onet_code, fallback)
            try:
                entries = _fetch(fallback)
            except OnetAPIError:
                # A genuinely task-less occupation has no sub-code to fall back
                # to, and asking for one is a 404.  Measured over the whole
                # catalog 2026-09-16: 74 of 1,016 occupations have no task data
                # -- all 19 of the 55-0000 Military Specific family, and the
                # "..., All Other" residual codes (11-9039.00, 43-9199.00, ...)
                # spread across every other family.  Some of those do have a
                # .01 with data, which is why the fallback is attempted at all;
                # the rest 404.  An occupation with no tasks is a thinner role
                # document, not a failed fetch, so this must not propagate.
                _log.debug("tasks sub-code %s does not exist", fallback)
                entries = []
        if not entries:
            _log.warning("tasks empty for %s (no fallback data)", onet_code)

        result = [
            Task(
                task_id=str(t.get("id", "")),
                title=t.get("title", ""),
                importance=float(t.get("importance", 0.0)),
                category=t.get("category", ""),
            )
            for t in entries
        ]
        result.sort(key=lambda t: t.importance, reverse=True)
        _occ_cache_set(cache_key, result)
        return result

    def get_hot_technologies(self, onet_code: str) -> list[str]:
        """Return *onet_code*'s hot technologies, most in-demand first.

        v2 endpoint: ``/online/occupations/[code]/hot_technology``.

        **Why not get_tech_skills(hot_only=True)**, which already returns the
        same tools from /details/technology_skills for the same one request:
        that method returns a ``set`` of ``.lower()``-ed names.  A set has no
        order, so "the top N" is unanswerable, and Python's per-process string
        hash randomisation means iterating one twice in two processes yields two
        different orders -- which would make a corpus artifact built from it
        irreproducible.  This endpoint returns the tools ranked by the share of
        job postings mentioning them (measured 2026-09-16: Data Scientists leads
        Python 66%, SQL 51%, R 34%) and preserves O*NET's own capitalisation.

        Returns ``[]`` for an occupation with no hot technologies rather than
        raising -- the endpoint answers 200 with ``total: 0``, not 404
        (measured against the 55-0000 Military Specific family).

        Result is cached per onet_code for _OCC_CACHE_TTL seconds (24h).
        """
        cache_key = ("get_hot_technologies", onet_code, ())
        cached = _occ_cache_get(cache_key)
        if cached is not None:
            return list(cached)

        data = self._get(
            f"online/occupations/{onet_code}/hot_technology",
            params={"end": 100},
        )
        names = [
            ex["title"]
            for ex in (data.get("example") or [])
            if ex.get("title")
        ]
        _occ_cache_set(cache_key, names)
        return names

    def get_bright_outlook_occupations(self) -> list[Occupation]:
        """Return all Bright Outlook occupations, deduplicated across the three categories.

        Fetches /online/bright_outlook/ for category codes, then each category's
        occupations from /online/bright_outlook/[category_code].  Results are cached
        for _BRIGHT_OUTLOOK_CACHE_TTL seconds (24h) — the list changes only quarterly.
        On any OnetAPIError returns the stale cache (possibly empty) so the caller
        can fall back to profile-seeded search.

        /online/bright_outlook returns a bare JSON array of {href, code, title}
        (not wrapped in an object) — unlike every other list endpoint in this
        client. Confirmed against the live v2 API.  The array also includes a
        4th "All Bright Outlook Occupations" meta-entry with no "code" key
        (only href/title) — skipped rather than looped over, since it's a
        convenience alias for the same 3 categories, not a distinct category.
        """
        global _BRIGHT_OUTLOOK_CACHE, _BRIGHT_OUTLOOK_CACHE_TS
        now = time.monotonic()
        if _BRIGHT_OUTLOOK_CACHE and now - _BRIGHT_OUTLOOK_CACHE_TS < _BRIGHT_OUTLOOK_CACHE_TTL:
            return _BRIGHT_OUTLOOK_CACHE
        try:
            categories_data = self._get("online/bright_outlook")
            categories = [cat["code"] for cat in categories_data if cat.get("code")]
            seen: set[str] = set()
            result: list[Occupation] = []
            for category_code in categories:
                # end=100 per category: categories can hold 300+ occupations and the
                # API defaults to a 20-item page, same rationale as get_job_family_occupations.
                cat_data = self._get(f"online/bright_outlook/{category_code}", params={"end": 100})
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

        **This endpoint returns a bare JSON array**, like /online/bright_outlook
        and unlike the wrapped list endpoints -- confirmed against the live v2
        API 2026-09-16, where the previous ``data.get("job_family")`` raised
        ``AttributeError: 'list' object has no attribute 'get'`` on every call.
        Both shapes are accepted here so a future re-wrap cannot break it again.

        The array also carries a meta-entry with a ``title`` and an ``href`` but
        **no ``code``** ("All Job Families"), exactly as the Bright Outlook
        array does; it is a convenience alias for the whole set, not a family,
        and is skipped rather than yielded as a family with an empty code.
        """
        data = self._get("online/job_families")
        raw = data if isinstance(data, list) else (data.get("job_family") or [])
        return [
            {"code": fam["code"], "title": fam.get("title", "")}
            for fam in raw
            if fam.get("code")
        ]

    def get_job_family_occupations(
        self,
        family_code: str,
        start: int = 1,
        end: int = 100,
    ) -> list[Occupation]:
        """Return one page of the occupations within a SOC job family.

        Requests entries ``start``..``end`` inclusive, 1-indexed, matching the
        API's own paging parameters.  The defaults reproduce the pre-2026-09-16
        behaviour exactly (first 100), so no existing caller changes.

        **One page is not the whole family.**  The docstring here used to claim
        the largest family has ~38 occupations; measured against the live v2 API
        2026-09-16, ``51-0000`` (Production) has **114**, so the default page
        silently drops 14 of them.  The 23 families total 1,016 occupations,
        which is the entire catalog (``/online/occupations`` reports the same
        1,016).  A caller that needs the *whole* family -- the corpus builder
        does; the scoring funnel deliberately does not -- must page, either on
        the ``total`` in the response or by requesting until a short page comes
        back.

        Args:
            family_code: SOC major-group code, e.g. "15-0000".
            start: 1-indexed first entry to return.
            end: 1-indexed last entry to return.

        Raises:
            OnetAPIError: On any HTTP error.
        """
        data = self._get(
            f"online/job_families/{family_code}",
            params={"start": start, "end": end},
        )
        return [
            Occupation(code=occ_data.get("code", ""), title=occ_data.get("title", ""))
            for occ_data in data.get("occupation", [])
        ]

    def get_all_occupations(self, start: int = 1, end: int = 100) -> list[dict]:
        """Return one page of the whole O*NET catalog, **with each Job Zone**.

        ``/online/occupations`` is the only bulk endpoint that carries Job Zone.
        Every other route to a zone is ``get_job_zone``, one request per
        occupation -- 1,016 requests for the catalog against **11 pages** here,
        which is why this exists (BUILD_PLAN F-3).

        Each dict has ``code``, ``title`` and ``zone``.  ``zone`` is the
        integer 1-5 or ``None`` when the record carries no zone block; a caller
        filtering on feasibility must decide what an unknown zone means rather
        than being handed a silent default.

        **Read ``zone.code``, never ``zone.title``.**  Measured against the live
        v2 API 2026-09-16: "Actors" comes back as ``{"code": 2, "title": "Job
        Zone 1-2: Very Little to Some Preparation Needed"}`` -- the title is
        sometimes a *range* label while the code is always one integer.
        Parsing the title would turn that occupation into two zones or none.

        Paging works exactly as ``get_job_family_occupations``: 1-indexed,
        inclusive, and one page is not the catalog.  The response carries
        ``total`` (1,016, measured 2026-09-16, matching the corpus row count);
        page until a short page comes back or ``start`` passes it.

        Deliberately **not** cached in ``_OCC_CACHE``.  That cache is keyed per
        occupation and capped at 2,048 entries; one page of 100 records would
        evict 100 per-occupation entries to store something the corpus tooling
        reads once and writes to a sidecar.

        Args:
            start: 1-indexed first entry to return.
            end: 1-indexed last entry to return.

        Raises:
            OnetAPIError: On any HTTP error.
            OnetRateLimitError: If 429s outlast the retry budget.
        """
        data = self._get("online/occupations", params={"start": start, "end": end})
        page: list[dict] = []
        for occ in data.get("occupation", []):
            code = occ.get("code", "")
            if not code:
                continue
            zone_block = occ.get("zone")
            zone: int | None = None
            if isinstance(zone_block, dict) and zone_block.get("code") is not None:
                try:
                    zone = int(zone_block["code"])
                except (TypeError, ValueError):
                    zone = None
            page.append({"code": code, "title": occ.get("title", ""), "zone": zone})
        return page

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
