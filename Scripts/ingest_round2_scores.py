"""Load round-2 LLM draws into a LOCAL ground-truth lane database (never production).

Reads the draw files causal_graph/run_round2_scoring.py writes
(Solverah_IP/analysis_s58/results/round2/<packet>_draw<n>.json) and stores each draw as its own
scorer_run, with its SCORED dimensions and their citations, via
company_score_store.ingest_extractor_result -- the same write path as backfill_company_scores.

ABSTENTIONS ARE NOT ROWS. The company score table's score column is NOT NULL, and Sebastian chose
(2026-09-29) not to change the product schema for this. An "insufficient evidence" dimension
is therefore recorded in the run's notes ("insufficient evidence on: ...") and in full in the
draw JSON, which stays the complete record. Read abstention counts from the JSON, not the DB.

THE DATABASE IS GUARDED. The repo's .env carries the PRODUCTION DATABASE_URL, so this script:
  * never reads .env (SOLVERAH_IGNORE_DOTENV is forced on before the app is imported);
  * requires the URL explicitly (--database-url or $DATABASE_URL), with no fallback;
  * refuses unless the host is local, the query string cannot redirect the driver (the checks
    are causal_graph/v1_model/devfit/guard.py's, imported, not copied), and the database name
    starts with `solverah_gt`;
  * re-checks the URL the app actually configured, after import, before writing.

    python -m Scripts.ingest_round2_scores \
        --database-url postgresql://solverah:solverah@localhost:5433/solverah_gt2 [--dry-run]

Every print is ASCII.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (REPO_ROOT, REPO_ROOT / "causal_graph", REPO_ROOT / "causal_graph" / "v1_model" / "devfit"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from guard import LOCAL_HOSTS, SAFE_QUERY_KEYS  # noqa: E402

LANE_DB_PREFIX = "solverah_gt"
RESULTS = REPO_ROOT / "Solverah_IP" / "analysis_s58" / "results" / "round2"


class UnsafeDatabaseError(RuntimeError):
    pass


def assert_lane_database(url: str | None) -> str:
    """guard.py's host and query-string rules, with this lane's database prefix."""
    if not url:
        raise UnsafeDatabaseError("no database URL -- pass --database-url or set DATABASE_URL; "
                                  "this script never falls back to .env (it holds PRODUCTION)")
    if os.environ.get("APP_ENV", "").strip().lower() == "production":
        raise UnsafeDatabaseError("APP_ENV=production")
    parts = urlsplit(url)
    bad = sorted(k for k, _ in parse_qsl(parts.query, keep_blank_values=True)
                 if k.lower() not in SAFE_QUERY_KEYS)
    if bad:
        raise UnsafeDatabaseError(f"query parameter(s) {bad} can redirect the driver")
    if (parts.hostname or "").lower() not in LOCAL_HOSTS:
        raise UnsafeDatabaseError(f"host {parts.hostname!r} is not local")
    if not parts.path.lstrip("/").startswith(LANE_DB_PREFIX):
        raise UnsafeDatabaseError(f"database {parts.path.lstrip('/')!r} is not a "
                                  f"{LANE_DB_PREFIX}* lane database")
    return url


def draw_records(results: Path = RESULTS) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(results.glob("P-*_draw*.json"))]


def to_ingest_args(doc: dict) -> dict:
    """One draw file -> the keyword arguments for ingest_extractor_result (minus company_id)."""
    run_at = datetime.datetime.fromisoformat(doc["run_at"].replace("Z", "+00:00"))
    dims = doc["result"]["dimensions"]
    skipped = [d["dimension"] for d in dims if d["score"] is None]
    cites = doc.get("citations") or []
    notes = f"round2 {doc['packet_id']} draw {doc['draw']}; anchors {doc.get('anchors_hash')}"
    if skipped:
        notes += "; insufficient evidence on: " + ", ".join(skipped)
    return {
        "as_of": run_at.date(),
        "run": {
            "model": doc["model"],
            "temperature": 1.0 if doc["temperature_honored"] else None,
            "temperature_honored": doc["temperature_honored"],
            "reasoning_effort": doc["reasoning_effort"],
            "rubric_version": doc["rubric_version"],
            "packet_version": doc["packet_version"],
            "run_at": run_at,
            "notes": notes,
        },
        "dimensions": [
            {
                "dimension_key": d["dimension"], "score": d["score"], "confidence": d["confidence"],
                "citations": [{"quote_text": c["quote"], "matched": c["matched"],
                               "matched_excerpt_id": c["matched_eid"] if c["matched"] else None,
                               "source_tag": c["source_tag"] if c["matched"] else None}
                              for c in cites if c["dimension"] == d["dimension"]],
            }
            for d in dims if d["score"] is not None
        ],
        "skipped": skipped,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--database-url", default=None)
    ap.add_argument("--results", type=Path, default=RESULTS)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    url = assert_lane_database(a.database_url or os.environ.get("DATABASE_URL"))
    from run_round2_scoring import ROUND2_COMPANIES

    docs = draw_records(a.results)
    plans = [(d, to_ingest_args(d)) for d in docs]
    for d, args in plans:
        print(f"  {d['packet_id']} draw {d['draw']}: {len(args['dimensions'])} scored, "
              f"{len(args['skipped'])} insufficient")
    if a.dry_run or not plans:
        print(f"{'DRY RUN' if a.dry_run else 'NOTHING TO DO'}: {len(plans)} draw file(s) "
              f"in {a.results}")
        return 0

    os.environ["SOLVERAH_IGNORE_DOTENV"] = "1"
    os.environ["DATABASE_URL"] = url
    from app import app
    assert_lane_database(str(app.config.get("SQLALCHEMY_DATABASE_URI")))  # what the driver dials

    import company_score_store
    from Scripts.backfill_company_scores import _company_id_for
    with app.app_context():
        for d, args in plans:
            company_id = _company_id_for(ROUND2_COMPANIES[d["packet_id"]][0])
            summary = company_score_store.ingest_extractor_result(
                company_id=company_id, as_of=args["as_of"], run=args["run"],
                dimensions=args["dimensions"], source="scraped", is_ground_truth=True)
            print(f"  stored {d['packet_id']} draw {d['draw']} -> scorer_run "
                  f"{summary['scorer_run_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
