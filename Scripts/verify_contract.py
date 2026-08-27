"""Re-run the recorded scenario and diff it against the baseline.

    python -m Scripts.verify_contract

Exit code 0 means the wire did not move. Anything else prints a unified diff of
the first differing response and exits 1.

The comparison is on the masked response *text*, not on parsed JSON -- see
`capture_contract.py` for why. It also compares status, mimetype, and the names of
the cookies each response sets, because a contract that returns the same body under
a different status is still a broken contract.
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from Scripts.capture_contract import BASELINE, run_scenario

_COMPARED = ("step", "method", "path", "status", "mimetype", "cookies_set", "body")


def _diff(recorded: List[Dict[str, Any]], observed: List[Dict[str, Any]]) -> List[str]:
    """Return one human-readable report per difference, empty if there are none."""
    problems: List[str] = []

    if len(recorded) != len(observed):
        problems.append(
            "step count changed: baseline has %d, this run produced %d.\n"
            "  baseline: %s\n  this run: %s"
            % (
                len(recorded),
                len(observed),
                [r["step"] for r in recorded],
                [o["step"] for o in observed],
            )
        )

    for want, got in zip(recorded, observed):
        for field in _COMPARED:
            if want.get(field) == got.get(field):
                continue
            if field == "body":
                problems.append(
                    "%s %s %s -- body differs:\n%s"
                    % (
                        want["step"],
                        want["method"],
                        want["path"],
                        "\n".join(
                            difflib.unified_diff(
                                str(want.get(field)).splitlines(),
                                str(got.get(field)).splitlines(),
                                fromfile="baseline",
                                tofile="this run",
                                lineterm="",
                            )
                        )
                        or "  (no line-level diff; check trailing whitespace)",
                    )
                )
            else:
                problems.append(
                    "%s %s %s -- %s: baseline %r, this run %r"
                    % (want["step"], want["method"], want["path"], field,
                       want.get(field), got.get(field))
                )
    return problems


def main(argv: List[str]) -> int:
    source = Path(argv[1]) if len(argv) > 1 else BASELINE
    if not source.exists():
        print(
            "no baseline at %s -- run `python -m Scripts.capture_contract` on the "
            "commit before the change first." % source,
            file=sys.stderr,
        )
        return 2

    recorded = json.loads(source.read_text(encoding="utf-8"))
    observed = run_scenario()
    problems = _diff(recorded, observed)

    if not problems:
        print("contract diff: 0 differences across %d responses" % len(observed))
        return 0

    print("contract diff: %d difference(s)\n" % len(problems), file=sys.stderr)
    for problem in problems:
        print(problem, file=sys.stderr)
        print("", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
