"""Load-test BASELINE for the Solverah API — numbers, not fixes.

Runs a fixed concurrency ladder (1, 5, 10, 25 virtual users, 60s each) against
four endpoints on the LOCAL compose stack and prints p50/p95/p99, RPS, and an
error breakdown per step.  Results also land in a JSON file (--out).

Scenarios
    session     GET  /api/v1/auth/session            (the boot path)
    dashboard   GET  /api/v1/me/dashboard            (Redis-cached; cold AND warm measured)
    matches     GET  /api/v1/me/matches              (the full-scan path, P0-2's subject)
    submit      POST /api/v1/assessments/core/submissions  (the surviving sync write)

Usage (see docs/LOAD_BASELINE.md for the full recipe)
    docker compose -f infra/docker/compose.yml -f Scripts/load_baseline.override.yml \
        up -d db redis api worker
    docker compose -f infra/docker/compose.yml exec api \
        python -m company_culture_LLM.seed_from_generated_xlsx
    # venv OUTSIDE the repo (an in-repo venv fails the guard tests):
    python -m venv %TEMP%/solverah-loadenv && <activate> && pip install -r requirements-dev.txt
    python Scripts/load_baseline.py --label dev-1w4t

Safety: this script refuses any non-local target.  ``_refuse_non_local_target``
below is modeled on ``tests/conftest.py::_refuse_non_local_database`` — same
idiom, same reasoning: every guarantee that hammering the API and writing junk
users into the database is safe rests on the target being a local, disposable
compose stack, and nothing else checks that.  There is deliberately no override
flag; if a remote load target is ever genuinely wanted, that is a considered
change to this function, not a variable someone exports at 2am.  In particular
nothing containing ``render.com`` (or any other non-loopback host) can ever be
a target.

Rate limiter: the limiter is per-IP (``get_remote_address``) with global
defaults of 50/hour — a naive run from one IP measures the limiter, not the
API.  This script does NOT turn the limiter off (no such switch exists, and we
do not add one).  Instead it sends a unique ``X-Forwarded-For`` per request,
and the companion override file sets ``TRUSTED_PROXY_COUNT=1`` — an existing,
documented env knob (solverah/factory.py:126-138) — so every request lands in
its own limiter bucket.  The limiter's Redis lookup therefore stays in the
measured path (it runs on every request); only the counters never fill.  Any
429 that still appears is reported in its own column.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine
from urllib.parse import urlsplit

import httpx

DEFAULT_BASE_URL = "http://localhost:5000"
DEFAULT_DB_URL = "postgresql://solverah:solverah@localhost:5433/solverah"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"

LADDER = (1, 5, 10, 25)
STEP_SECONDS = 60
PASSWORD = "LoadBaseline#2026"  # 12+ chars, upper, lower, digit, symbol (validators.py)
EMAIL_TEMPLATE = "loadbase-{:03d}@example.test"
DASHBOARD_CACHE_PREFIX = "solverah:v1:dashboard:"  # solverah/infra/cache.py:82

# Client timeout deliberately ABOVE gunicorn's 30s timeout so a worker kill
# surfaces as a connection error / 5xx (trap 4) instead of being masked by a
# client-side timeout.
CLIENT_TIMEOUT = httpx.Timeout(35.0, connect=10.0)


def _refuse_non_local_target(raw_url: str, what: str) -> None:
    """Abort unless *raw_url* points at a local, disposable target.

    Modeled on ``tests/conftest.py::_refuse_non_local_database``: loopback
    hosts only, no override flag by design.

    Raises:
        SystemExit: if the URL is unparseable or names a non-local host.
    """
    try:
        host = urlsplit(raw_url).hostname
    except ValueError as exc:
        raise SystemExit(
            f"{what} URL {raw_url!r} could not be parsed, so it cannot be "
            f"checked for safety. Refusing to run. ({exc})"
        )
    if host is None:
        raise SystemExit(f"{what} URL {raw_url!r} names no host. Refusing to run.")
    if host == "localhost" or host.endswith(".localhost"):
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise SystemExit(
        f"{what} URL {raw_url!r} names non-local host {host!r}. This script "
        "seeds junk users and generates load; it only ever targets the local "
        "compose stack. There is no override flag, deliberately — see "
        "tests/conftest.py::_refuse_non_local_database for the reasoning."
    )


_xff_counter = 0


def _next_xff() -> str:
    """A unique fake client IP per request (10.0.0.0/8, never loopback).

    Only takes effect when the api container runs with TRUSTED_PROXY_COUNT=1
    (Scripts/load_baseline.override.yml); with the compose default of 0 the
    header is ignored and the limiter answers the load test instead.
    """
    global _xff_counter
    _xff_counter += 1
    n = _xff_counter
    return f"10.{(n >> 16) & 0xFF}.{(n >> 8) & 0xFF}.{n & 0xFF}"


@dataclass
class VirtualUser:
    index: int
    email: str
    client: httpx.AsyncClient
    csrf_token: str = ""
    responses: dict[str, str] = field(default_factory=dict)  # core-form token -> option key
    user_id: int | None = None


@dataclass
class StepResult:
    concurrency: int
    wall_seconds: float
    latencies_ms: list[float] = field(default_factory=list)  # 2xx only
    ok: int = 0
    rate_limited: int = 0
    other_4xx: int = 0
    server_5xx: int = 0
    timeouts: int = 0
    conn_errors: int = 0

    @property
    def total(self) -> int:
        return (self.ok + self.rate_limited + self.other_4xx + self.server_5xx
                + self.timeouts + self.conn_errors)

    def percentile(self, p: float) -> float | None:
        if not self.latencies_ms:
            return None
        xs = sorted(self.latencies_ms)
        k = max(0, min(len(xs) - 1, round(p / 100 * len(xs) + 0.5) - 1))
        return xs[k]

    def row(self) -> dict[str, Any]:
        return {
            "concurrency": self.concurrency,
            "requests": self.total,
            "rps": round(self.total / self.wall_seconds, 1) if self.wall_seconds else 0,
            "p50_ms": round(self.percentile(50), 1) if self.latencies_ms else None,
            "p95_ms": round(self.percentile(95), 1) if self.latencies_ms else None,
            "p99_ms": round(self.percentile(99), 1) if self.latencies_ms else None,
            "mean_ms": round(statistics.fmean(self.latencies_ms), 1) if self.latencies_ms else None,
            "ok": self.ok,
            "http_429": self.rate_limited,
            "other_4xx": self.other_4xx,
            "http_5xx": self.server_5xx,
            "timeouts": self.timeouts,
            "conn_errors": self.conn_errors,
        }


RequestFn = Callable[[VirtualUser], Coroutine[Any, Any, httpx.Response]]


async def _measure_once(user: VirtualUser, fn: RequestFn, result: StepResult) -> None:
    t0 = time.perf_counter()
    try:
        resp = await fn(user)
    except httpx.TimeoutException:
        result.timeouts += 1
        return
    except httpx.HTTPError:
        result.conn_errors += 1
        return
    elapsed_ms = (time.perf_counter() - t0) * 1000
    if 200 <= resp.status_code < 300:
        result.ok += 1
        result.latencies_ms.append(elapsed_ms)
    elif resp.status_code == 429:
        result.rate_limited += 1
    elif 400 <= resp.status_code < 500:
        result.other_4xx += 1
    else:
        result.server_5xx += 1


async def run_step(users: list[VirtualUser], concurrency: int, duration: float,
                   fn: RequestFn) -> StepResult:
    result = StepResult(concurrency=concurrency, wall_seconds=duration)
    deadline = time.monotonic() + duration
    start = time.monotonic()

    async def vu_loop(user: VirtualUser) -> None:
        while time.monotonic() < deadline:
            await _measure_once(user, fn, result)

    await asyncio.gather(*(vu_loop(u) for u in users[:concurrency]))
    result.wall_seconds = time.monotonic() - start
    return result


# ---------------------------------------------------------------- scenarios

def scenario_session(base: str) -> RequestFn:
    async def fn(u: VirtualUser) -> httpx.Response:
        return await u.client.get(f"{base}/api/v1/auth/session",
                                  headers={"X-Forwarded-For": _next_xff()})
    return fn


def scenario_dashboard(base: str) -> RequestFn:
    async def fn(u: VirtualUser) -> httpx.Response:
        return await u.client.get(f"{base}/api/v1/me/dashboard",
                                  headers={"X-Forwarded-For": _next_xff()})
    return fn


def scenario_matches(base: str) -> RequestFn:
    async def fn(u: VirtualUser) -> httpx.Response:
        return await u.client.get(f"{base}/api/v1/me/matches", params={"limit": 20},
                                  headers={"X-Forwarded-For": _next_xff()})
    return fn


def scenario_submit(base: str) -> RequestFn:
    async def fn(u: VirtualUser) -> httpx.Response:
        return await u.client.post(
            f"{base}/api/v1/assessments/core/submissions",
            json={"responses": u.responses},
            headers={"X-Forwarded-For": _next_xff(), "X-CSRF-TOKEN": u.csrf_token},
        )
    return fn


SCENARIOS: dict[str, Callable[[str], RequestFn]] = {
    "session": scenario_session,
    "dashboard": scenario_dashboard,
    "matches": scenario_matches,
    "submit": scenario_submit,
}

# ------------------------------------------------------------------ seeding

CULTURE_PREFS_SQL = """
INSERT INTO profiles (user_id, completeness, extra, version)
VALUES (%s, 0, %s::jsonb, 0)
ON CONFLICT (user_id) DO UPDATE SET extra = profiles.extra || excluded.extra
"""


def _culture_prefs(i: int) -> dict[str, Any]:
    # Shape per packages/ml/culture/scoring.py; small per-user variation so
    # sort keys differ. Not settable over HTTP (validators.ALLOWED_PROFILE_FIELDS
    # drops it), hence the direct write into profiles.extra.
    v = (i % 10) / 20  # 0.00 .. 0.45
    return {
        "culture_preferences": {
            "empathy": round(0.3 + v, 2),
            "creative_drive": round(0.75 - v, 2),
            "adaptability": 0.6,
            "futuristic": round(0.25 + v, 2),
            "harmony": 0.5,
            "data_orientation": round(0.7 - v, 2),
            "work_environment": ["collaborative"],
            "pace": ("fast", "moderate", "slow")[i % 3],
        }
    }


async def seed_users(base: str, db_url: str, count: int) -> list[VirtualUser]:
    import psycopg

    users: list[VirtualUser] = []
    for i in range(count):
        email = EMAIL_TEMPLATE.format(i)
        client = httpx.AsyncClient(timeout=CLIENT_TIMEOUT)
        users.append(VirtualUser(index=i, email=email, client=client))

    with psycopg.connect(db_url, autocommit=True) as conn:
        for u in users:
            # Register (5/min per IP -> unique XFF each; 4xx tolerated: the
            # account may exist from a previous run, login below decides).
            r = await u.client.post(
                f"{base}/api/v1/auth/register",
                json={"email": u.email, "password": PASSWORD,
                      "terms_accepted": True, "name": f"Load Base {u.index:03d}"},
                headers={"X-Forwarded-For": _next_xff()},
            )
            if r.status_code not in (201, 400, 409):
                raise SystemExit(f"register {u.email}: unexpected {r.status_code} {r.text[:200]}")

            row = conn.execute(
                "SELECT id, confirmation_token FROM users WHERE email = %s", (u.email,)
            ).fetchone()
            if row is None:
                raise SystemExit(f"{u.email}: no users row after register")
            u.user_id, code = row
            if code:  # None once confirmed (auth_service clears it)
                r = await u.client.post(
                    f"{base}/api/v1/auth/email/verify",
                    json={"email": u.email, "code": code},
                    headers={"X-Forwarded-For": _next_xff()},
                )
                if r.status_code != 200:
                    raise SystemExit(f"verify {u.email}: {r.status_code} {r.text[:200]}")

            r = await u.client.post(
                f"{base}/api/v1/auth/login",
                json={"email": u.email, "password": PASSWORD},
                headers={"X-Forwarded-For": _next_xff()},
            )
            if r.status_code != 200:
                raise SystemExit(f"login {u.email}: {r.status_code} {r.text[:200]}")
            u.csrf_token = r.json().get("csrfToken", "")

            # Core form: cache the 24 item tokens for the submit scenario.
            r = await u.client.get(f"{base}/api/v1/assessments/core/form",
                                   headers={"X-Forwarded-For": _next_xff()})
            if r.status_code != 200:
                raise SystemExit(
                    f"core form {u.email}: {r.status_code} {r.text[:200]} — is "
                    "SOLVERAH_FORM_TOKEN_SECRET set in the api container? "
                    "(Scripts/load_baseline.override.yml sets it)"
                )
            form = r.json()
            u.responses = {
                item["token"]: item["options"][0]["key"]
                for block in form["blocks"] for item in block["items"]
            }
            if len(u.responses) != 24:
                raise SystemExit(f"{u.email}: form yielded {len(u.responses)} tokens, want 24")

            # matches prerequisite: culture_preferences into profiles.extra.
            conn.execute(CULTURE_PREFS_SQL, (u.user_id, json.dumps(_culture_prefs(u.index))))
    return users


def flush_dashboard_cache(redis_url: str) -> int:
    import redis as redis_lib

    r = redis_lib.Redis.from_url(redis_url)
    deleted = 0
    for key in r.scan_iter(match=DASHBOARD_CACHE_PREFIX + "*"):
        r.delete(key)
        deleted += 1
    return deleted


# ---------------------------------------------------------------- reporting

COLUMNS = ("concurrency", "requests", "rps", "p50_ms", "p95_ms", "p99_ms",
           "ok", "http_429", "other_4xx", "http_5xx", "timeouts", "conn_errors")


def print_table(rows: list[dict[str, Any]]) -> None:
    print("| " + " | ".join(COLUMNS) + " |")
    print("|" + "---|" * len(COLUMNS))
    for row in rows:
        print("| " + " | ".join(str(row.get(c, "")) for c in COLUMNS) + " |")


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


# --------------------------------------------------------------------- main

async def amain(args: argparse.Namespace) -> None:
    base = args.base_url.rstrip("/")

    # Warmup: /healthz is auth-free and rate-limit exempt (factory.py:362).
    async with httpx.AsyncClient(timeout=CLIENT_TIMEOUT) as probe:
        for attempt in range(30):
            try:
                r = await probe.get(f"{base}/healthz")
                if r.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(2)
        else:
            raise SystemExit(f"{base}/healthz never answered 200; is the compose stack up?")

    print(f"Seeding {args.users} users ...", flush=True)
    users = await seed_users(base, args.db_url, args.users)

    # Preflight: one request per scenario, statuses must make sense before we
    # spend 16 minutes measuring garbage.
    u0 = users[0]
    checks = {
        "session": await scenario_session(base)(u0),
        "dashboard": await scenario_dashboard(base)(u0),
        "matches": await scenario_matches(base)(u0),
        "submit": await scenario_submit(base)(u0),
    }
    scan_size = None
    for name, resp in checks.items():
        print(f"  preflight {name}: {resp.status_code}")
        if resp.status_code != 200:
            raise SystemExit(f"preflight {name} answered {resp.status_code}: {resp.text[:300]}")
    scan_size = checks["matches"].json().get("total_companies_scored")
    print(f"  matches total_companies_scored = {scan_size}")
    if not scan_size:
        print("  WARNING: 0 companies scored — seed companies first "
              "(python -m company_culture_LLM.seed_from_generated_xlsx in the api container)")

    results: dict[str, Any] = {
        "label": args.label,
        "base_url": base,
        "date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": _git_commit(),
        "users_seeded": args.users,
        "step_seconds": args.duration,
        "ladder": list(args.ladder),
        "matches_total_companies_scored": scan_size,
        "scenarios": {},
    }

    scenario_names = args.scenarios.split(",")
    for name in scenario_names:
        if name not in SCENARIOS:
            raise SystemExit(f"unknown scenario {name!r}; choose from {sorted(SCENARIOS)}")

    for name in scenario_names:
        fn = SCENARIOS[name](base)
        rows: list[dict[str, Any]] = []
        print(f"\n=== scenario: {name} ===", flush=True)

        if name == "dashboard":
            # Trap 2: first hit warms the Redis cache, the rest measure Redis.
            # Cold = one sequential GET per user immediately after flushing the
            # dashboard keys; everything in the ladder below is warm.
            deleted = flush_dashboard_cache(args.redis_url)
            print(f"  flushed {deleted} dashboard cache keys; measuring cold hits ...")
            cold = StepResult(concurrency=1, wall_seconds=0)
            t0 = time.monotonic()
            for u in users:
                await _measure_once(u, fn, cold)
            cold.wall_seconds = time.monotonic() - t0
            row = cold.row()
            row["concurrency"] = "cold(seq)"
            rows.append(row)
            print_table([row])

        for concurrency in args.ladder:
            if name == "dashboard":
                # Re-warm so a mid-ladder TTL expiry (300s default) does not
                # leak cold hits into the warm numbers.
                for u in users[:concurrency]:
                    await fn(u)
            print(f"  {concurrency} VUs x {args.duration}s ...", flush=True)
            step = await run_step(users, concurrency, args.duration, fn)
            rows.append(step.row())
        print_table([r for r in rows if r["concurrency"] != "cold(seq)"])
        results["scenarios"][name] = rows

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nresults written to {args.out}")

    for u in users:
        await u.client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--db-url", default=DEFAULT_DB_URL,
                        help="host-side URL of the compose DB (for OTP reads and culture-pref seeding)")
    parser.add_argument("--redis-url", default=DEFAULT_REDIS_URL,
                        help="host-side URL of the compose Redis (for cold-cache flushes)")
    parser.add_argument("--users", type=int, default=max(LADDER))
    parser.add_argument("--ladder", type=lambda s: tuple(int(x) for x in s.split(",")),
                        default=LADDER)
    parser.add_argument("--duration", type=float, default=STEP_SECONDS)
    parser.add_argument("--scenarios", default=",".join(SCENARIOS),
                        help="comma-separated subset of: " + ",".join(SCENARIOS))
    parser.add_argument("--label", default="dev-1w4t",
                        help="config label recorded in the results (e.g. dev-1w4t, prodcfg-3w8t)")
    parser.add_argument("--out", default="load_baseline_results.json")
    args = parser.parse_args()

    if args.users < max(args.ladder):
        parser.error(f"--users must be >= max ladder step ({max(args.ladder)})")

    _refuse_non_local_target(args.base_url, "base")
    _refuse_non_local_target(args.db_url, "database")
    _refuse_non_local_target(args.redis_url, "redis")

    asyncio.run(amain(args))


if __name__ == "__main__":
    sys.exit(main())
