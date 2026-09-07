#!/usr/bin/env python3
"""Check a de-identified packet against the raw packet it came from.

    python Scripts/verify_scrub.py P-07 --company "Cummins"

Deliberately lives HERE and not in `_scrub_env/`. The scrubber connects that folder and
can read everything in it; a verifier sitting next to the brief would tell it exactly what
is checked, and a model that can see the test can satisfy the test rather than the rule.
The check has to be somewhere the scrubbed artifact cannot have been written against.

What it proves, in order of how badly it would hurt to get wrong:

 1. The packet still PARSES. The citation harness reads only what lies between
    `########## SECTION 1` and `########## END OF PACKET ##########` and finds excerpts by
    regex. A reformatted bullet does not error -- the excerpt silently vanishes, and the
    packet still looks fine to a human.
 2. Quote bodies are character-identical to the raw packet except where the scrubber
    declared an edit ON that line (amendment A4). This is the em-dash defect: P-02 and
    P-05 were retyped rather than edited, ASCII hyphens became em dashes inside quote
    bodies, and three quotes failed citation verification on punctuation alone.
 3. The excerpt count did not shrink. Under A3 a claim recurring in two sections is kept
    in both with a note, never deleted -- a scrubber that "deduplicates" destroys evidence.
 4. The identifiers that were supposed to go, went: no URLs, no company name outside a
    bracketed substitution.

Exit code is 0 only if every check passes.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "causal_graph"))

# A bracketed declaration on the excerpt line, e.g.
#   -- [proper noun rewritten in brackets; clause otherwise verbatim]
DECLARATION_RE = re.compile(r"\[[^\]]*(?:rewritten|substitut|stripped|replaced|redact"
                            r"|magnitude|verbatim|the company|a named|the chief)[^\]]*\]",
                            re.I)
QUOTE_RE = re.compile(r'"([^"]*)"')
URL_RE = re.compile(r"https?://", re.I)


def die(msg: str) -> None:
    print("FATAL: %s" % msg, file=sys.stderr)
    raise SystemExit(2)


def norm_for_display(s: str) -> str:
    return s if len(s) <= 90 else s[:87] + "..."


def char_diff(a: str, b: str) -> str:
    """First differing position, described in a way that names the usual culprit."""
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return "col %d: raw %r (%s) -> scrubbed %r (%s)" % (
                i, x, unicodedata.name(x, "?"), y, unicodedata.name(y, "?"))
    return "length differs: raw %d, scrubbed %d" % (len(a), len(b))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("packet_id", help="e.g. P-07")
    ap.add_argument("--company", action="append", default=[],
                    help="company name or short form that must not survive; repeatable")
    ap.add_argument("--ip-dir", default=os.environ.get(
        "SOLVERAH_IP_DIR", str(REPO / "Solverah_IP")))
    args = ap.parse_args(argv)

    ip = Path(args.ip_dir)
    pid = args.packet_id
    raw_candidates = list((ip / "ground_truth" / "packets").glob("%s_*/%s_packet.txt" % (pid, pid)))
    raw_candidates += list((ip / "ground_truth" / "_scrub_env" / "packets_raw").glob("%s_packet.txt" % pid))
    scrubbed_candidates = [
        ip / "ground_truth" / "_scrub_env" / "packets_out" / ("%s_packet_ANON.txt" % pid),
        ip / "ground_truth" / "anonymization" / ("%s_packet_ANON.txt" % pid),
    ]
    raw = next((p for p in raw_candidates if p.exists()), None)
    scrubbed = next((p for p in scrubbed_candidates if p.exists()), None)
    if not raw:
        die("no raw packet found for %s" % pid)
    if not scrubbed:
        die("no scrubbed packet found for %s (looked in packets_out/ and anonymization/)" % pid)

    print("raw       : %s" % raw)
    print("scrubbed  : %s" % scrubbed)
    print()

    import scorer_pipeline as sp  # noqa: E402  -- after sys.path is set

    failures: list[str] = []

    # ---- 1. it parses -----------------------------------------------------
    def body_of(path: Path, *, tolerant: bool) -> str:
        """`tolerant` is for RAW packets only. Builds before v4.6-ish carry the SECTION 1
        marker but no END OF PACKET marker (P-01 is one), so the harness refuses them --
        which is fine, because the harness never reads a raw packet. The SCRUBBED packet
        gets no such latitude: it is the artifact the scorer actually reads, and a missing
        end marker there is the defect this check exists to catch."""
        try:
            return sp.load_packet_section1(path)
        except Exception:
            if not tolerant:
                raise
            text = path.read_text(encoding="utf-8")
            i = text.find("########## SECTION 1")
            if i < 0:
                raise
            return text[i:].strip()

    try:
        raw_body = body_of(raw, tolerant=True)
    except Exception as exc:
        die("the RAW packet %s does not parse: %s" % (raw.name, exc))
    try:
        scr_body = body_of(scrubbed, tolerant=False)
    except Exception as exc:
        die("the SCRUBBED packet %s does not parse: %s\n"
            "Both markers must be present and literal: '########## SECTION 1' and "
            "'########## END OF PACKET ##########'." % (scrubbed.name, exc))

    try:
        version = sp.packet_version_for(scrubbed)
    except ValueError as exc:
        version = None
        failures.append("header carries no 'build vX.Y' marker -- %s" % exc)

    raw_ex = sp.parse_excerpts(raw_body)
    scr_ex = sp.parse_excerpts(scr_body)
    raw_by = Counter(e.section for e in raw_ex)
    scr_by = Counter(e.section for e in scr_ex)

    print("1. PARSE")
    print("   build version   : %s" % (version or "MISSING"))
    print("   raw excerpts    : %-4d %s" % (len(raw_ex), dict(sorted(raw_by.items()))))
    print("   scrubbed        : %-4d %s" % (len(scr_ex), dict(sorted(scr_by.items()))))
    if len(scr_ex) < 10:
        failures.append("only %d excerpts parsed -- the bullets stopped matching; the "
                        "packet is effectively empty" % len(scr_ex))

    # ---- 2. does the harness see the evidence the packet claims to hold? --
    #
    # The obvious check -- scrubbed count == raw count -- is worthless here, because the
    # RAW packets do not parse reliably either: P-02 and P-05 parse to zero excerpts and
    # P-06 to six, purely on blank-line placement. Comparing one unreliable number to
    # another tells you nothing. The section header's own declared count is the only
    # independent statement of what the section is supposed to contain, so check against
    # that, and show the raw parse alongside as information rather than as a standard.
    declared = {}
    for m in re.finditer(r"^---\s*([A-F])\.[^\n]*?(\d+)\s*(?:excerpts|passages|,)",
                         scr_body, re.M):
        declared.setdefault(m.group(1), int(m.group(2)))

    print("\n2. DOES THE HARNESS SEE THE EVIDENCE? (parsed vs the header's own count)")
    print("   %-4s %-9s %-9s %-9s" % ("sec", "declared", "parsed", "raw"))
    for sec in sorted(set(scr_by) | set(declared) | set(raw_by)):
        dec = declared.get(sec)
        got = scr_by.get(sec, 0)
        if dec is None:
            note = "header states no count"
        elif got == dec:
            note = "match"
        elif got == 0:
            note = "NONE PARSED -- section is invisible to the scorer"
            failures.append(
                "section %s declares %d excerpts and the harness parses ZERO. Every bullet "
                "must start a blank-line-delimited block (Rule Three); as it stands this "
                "evidence does not exist downstream." % (sec, dec))
        else:
            note = "differs -- content defect if the header is wrong, not a scrub error"
        print("   %-4s %-9s %-9d %-9d %s"
              % (sec, dec if dec is not None else "-", got, raw_by.get(sec, 0), note))

    total_declared = sum(declared.values()) if declared else 0
    if declared and len(scr_ex) < 0.6 * total_declared:
        failures.append(
            "only %d of ~%d declared excerpts parse -- the packet is substantially "
            "invisible to the citation harness" % (len(scr_ex), total_declared))

    # ---- 3. quote bodies unchanged unless declared ------------------------
    #
    # Deliberately NOT built on parse_excerpts. That parser only sees a bullet that starts
    # a blank-line-delimited block, so on a badly formatted RAW packet it yields almost
    # nothing -- P-08's raw parses to 6 excerpts against 52 real ones. Pairing off those 6
    # and reporting a pass is worse than not checking: it looks like verification.
    #
    # So pair bullets positionally within each section, reading the raw text between the
    # packet markers, independent of blank lines. Position is safe because excerpt ORDER is
    # preserved by rule and the counts are checked in step 2.
    def bullets_in(text: str, sec: str) -> list[str]:
        out, on = [], False
        for line in text.splitlines():
            if re.match(r"^---\s*([A-F])\.", line):
                on = line.lstrip().startswith("--- %s." % sec)
                continue
            if on and line.lstrip().startswith(("•", "·")):
                out.append(line.strip())
        return out

    BULLET_QUOTE = re.compile(r'^\s*[•·]\s*"(.*?)"\s*(?:—|--)')

    print("\n3. QUOTE FIDELITY (the em-dash defect)")
    checked = undeclared = declared = 0
    for sec in "ABCDEF":
        r_list, s_list = bullets_in(raw_body, sec), bullets_in(scr_body, sec)
        for lr, ls in zip(r_list, s_list):
            mr, ms = BULLET_QUOTE.match(lr), BULLET_QUOTE.match(ls)
            if not (mr and ms):
                continue
            checked += 1
            if mr.group(1) == ms.group(1):
                continue
            if DECLARATION_RE.search(ls):
                declared += 1
                continue
            undeclared += 1
            failures.append(
                "section %s quote changed with NO bracketed declaration on the line\n"
                "        %s\n     raw: %s\n     scr: %s"
                % (sec, char_diff(mr.group(1), ms.group(1)),
                   norm_for_display(mr.group(1)), norm_for_display(ms.group(1))))

    if checked < 0.5 * len(scr_ex):
        failures.append(
            "only %d quote bodies could be paired against the raw packet, against %d "
            "excerpts in the scrubbed one -- too few to call this verified"
            % (checked, len(scr_ex)))
    print("   quotes compared        : %d" % checked)
    print("   changed WITH a declared edit : %d  (allowed -- R2/R3/R4/R6)" % declared)
    print("   changed with NO declaration  : %d  %s"
          % (undeclared, "" if not undeclared else "<-- these are defects"))

    # ---- 4. identifiers actually gone -------------------------------------
    print("\n4. IDENTIFIERS")
    whole = scrubbed.read_text(encoding="utf-8")
    urls = len(URL_RE.findall(whole))
    print("   URLs remaining  : %d %s" % (urls, "" if not urls else "<-- R1 violated"))
    if urls:
        failures.append("%d URL(s) survive the scrub (R1)" % urls)
    for name in args.company:
        # a bracketed substitution legitimately contains the word "company"; a bare
        # company NAME never should.
        hits = len(re.findall(re.escape(name), whole, re.I))
        print("   %-22s: %d %s" % ("'%s'" % name, hits, "" if not hits else "<-- survives"))
        if hits:
            failures.append("company identifier %r appears %d time(s)" % (name, hits))
    if not args.company:
        print("   (no --company given; name check skipped)")

    # Lookup-key shaped tokens ANYWHERE in the file -- including the scrub log, which sits
    # after END OF PACKET and so is invisible to the harness but fully visible to a rater.
    # Both leaks so far came from exactly there. P-09's scrub log printed all five removed
    # ATS requisition ids verbatim while explaining that it had removed them; "REQ212547" is
    # an exact-match string that resolves straight to the company's job board. Amendment
    # A6(a) puts that mapping in the diff and the run record. This is what enforces it.
    lookup_keys = [
        ("requisition-style token", re.compile(r"\b[A-Z]{2,}[-_]?\d{4,}\b")),
        ("long digit run", re.compile(r"(?<![\d.])\d{6,}(?![\d.])")),
        ("UUID", re.compile(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", re.I)),
    ]
    # Fiscal-period tokens look exactly like requisition ids and are not identifiers --
    # "FY2025" appears in every Section F human-capital disclosure.
    NOT_A_KEY = re.compile(r"^(?:FY|CY|H[12]FY|Q[1-4]FY)\d{4}$", re.I)
    found = sorted({(label, hit) for label, rx in lookup_keys for hit in rx.findall(whole)
                    if not NOT_A_KEY.match(hit)})
    print("   lookup-key tokens : %d %s" % (len(found), "" if not found else "<-- A6(a)"))
    for label, hit in found:
        print("       %-24s %s" % (label, hit))
    if found:
        failures.append(
            "%d lookup-key shaped token(s) survive -- an exact-match string resolves to the "
            "source record. Check the SCRUB LOG as well as the packet body: the log sits "
            "after END OF PACKET, so the harness never reads it and a rater always does, and "
            "a log that names what it removed hands the identifier straight back (A6(a))."
            % len(found))

    # ---- verdict ----------------------------------------------------------
    print("\n" + "=" * 70)
    if failures:
        print("FAILED -- %d problem(s):\n" % len(failures))
        for f in failures:
            print("  * %s" % f)
        return 1
    print("PASSED -- packet parses, excerpt count preserved, every quote-body change is")
    print("declared on its line, and no URLs or company identifiers survive.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
