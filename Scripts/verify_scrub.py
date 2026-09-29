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
            # Stop at SECTION 2 even though there is no END OF PACKET marker. Without this
            # the raw body runs to end of file and the QA sections' own bullets parse as
            # excerpts -- P-10's raw reported 5 excerpts in section F against a real 4,
            # which reads as an excerpt lost in the scrub and is nothing of the kind.
            j = text.find("########## SECTION 2", i)
            return (text[i:j] if j > 0 else text[i:]).strip()

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
    # A section header states one of two quite different things, and conflating them
    # invents defects. A, B and C carry the PROMPT'S RANGE -- "(5-8 excerpts)",
    # "(12-15, one per line...)" -- so those numbers are the minimum and maximum the build
    # was required to hit, not a count of what is there. D, E and F carry the builder's own
    # measured yield -- "(yield: 4 excerpts ...)", and D's is "3 passages / 5 excerpt lines",
    # where the second number is the one the harness should see.
    #
    # Reading a range bound as a declared count is what made P-08's section B look like a
    # header error. It is not: 11 parsed against "12-15" is a build that came in one review
    # under the required minimum, which is a different and more serious finding.
    RANGE_RE = re.compile(r"\((\d+)\s*[–—-]\s*(\d+)")
    YIELD_RE = re.compile(r"yield:\s*(?:\d+\s*\w+\s*/\s*)?(\d+)")
    spec = {}
    for m in re.finditer(r"^---\s*([A-F])\.([^\n]*)$", scr_body, re.M):
        sec, head = m.group(1), m.group(2)
        y, r = YIELD_RE.search(head), RANGE_RE.search(head)
        if y:
            spec.setdefault(sec, ("yield", int(y.group(1)), int(y.group(1))))
        elif r:
            spec.setdefault(sec, ("range", int(r.group(1)), int(r.group(2))))

    build_notes: list[str] = []
    print("\n2. DOES THE HARNESS SEE THE EVIDENCE?")
    print("   %-4s %-14s %-8s %-8s" % ("sec", "header says", "parsed", "raw"))
    for sec in sorted(set(scr_by) | set(spec) | set(raw_by)):
        got = scr_by.get(sec, 0)
        entry = spec.get(sec)
        if entry is None:
            says, note = "-", "header states nothing"
        else:
            kind, lo, hi = entry
            says = "yield %d" % lo if kind == "yield" else "range %d-%d" % (lo, hi)
            if got == 0:
                note = "NONE PARSED -- invisible to the scorer"
                failures.append(
                    "section %s is declared non-empty and the harness parses ZERO excerpts. "
                    "Every bullet must start a blank-line-delimited block (Rule Three); as "
                    "it stands this evidence does not exist downstream." % sec)
            elif kind == "yield":
                note = "match" if got == lo else "DIFFERS from the builder's own count"
                if got != lo:
                    build_notes.append(
                        "section %s: the builder's header says %d, the harness parses %d"
                        % (sec, lo, got))
            elif got < lo:
                note = "BELOW the prompt's minimum"
                build_notes.append(
                    "section %s holds %d against a required minimum of %d -- a build yield "
                    "shortfall the required-to-yield audit should have caught" % (sec, got, lo))
            elif got > hi:
                note = "ABOVE the prompt's maximum"
                build_notes.append(
                    "section %s holds %d against a maximum of %d -- over cap"
                    % (sec, got, hi))
            else:
                note = "within range"
        print("   %-4s %-14s %-8d %-8d %s" % (sec, says, got, raw_by.get(sec, 0), note))

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

    # The strict shape -- a dash straight after the closing quote -- is tried first, so every
    # bullet it paired before is compared exactly as before, inner quotes included (the lazy
    # match runs on to the quote mark that the dash follows).
    #
    # It used to be the ONLY shape, which silently dropped two common ones from the
    # comparison: a truncated review, `"..." [...]  -- [review]`, and a press quote with its
    # attribution after it, `"...," Name said.  -- [trade press]`. 5 of P-13's 55 bullets
    # went unchecked that way under a PASSED verdict, and the press shape is exactly where a
    # scrub edits names inside quotes. For those, cut the line where the attribution starts
    # (`-- [source]`) and take the quote up to its LAST closing mark before that, so a quote
    # with a quote inside it is compared whole. Matching to the FIRST closing mark instead
    # hides every edit after an inner quote -- tried on 2026-09-29, and P-13's declared-edit
    # count fell from 16 to 11 while "compared" went up. A bullet that still cannot be
    # paired is LISTED below, never dropped without a word.
    BULLET_QUOTE = re.compile(r'^\s*[•·]\s*"(.*?)"\s*(?:—|--)')
    ATTRIBUTION_START = re.compile(r'\s(?:—|--)\s+\[')
    QUOTE_TO_LAST_MARK = re.compile(r'^\s*[•·]\s*"(.*)"')

    def quote_of(line: str):
        m = BULLET_QUOTE.match(line)
        if m:
            return m
        cut = ATTRIBUTION_START.search(line)
        return QUOTE_TO_LAST_MARK.match(line[:cut.start()] if cut else line)

    print("\n3. QUOTE FIDELITY (the em-dash defect)")
    checked = undeclared = declared = 0
    not_compared: list[str] = []
    for sec in "ABCDEF":
        r_list, s_list = bullets_in(raw_body, sec), bullets_in(scr_body, sec)
        for lr, ls in zip(r_list, s_list):
            mr, ms = quote_of(lr), quote_of(ls)
            if not (mr and ms):
                # ASCII only: the bullet carries a bullet glyph and em dashes, and a print
                # of either dies on this machine's cp1252 console.
                shown = norm_for_display(ls.lstrip("•· ")).encode("ascii", "replace").decode()
                not_compared.append("section %s: %s" % (sec, shown))
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
    print("   not compared           : %d  %s"
          % (len(not_compared), "" if not not_compared else
             "<-- no opening quote to pair; check these by eye"))
    for line in not_compared:
        print("       %s" % line)

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
    # Build notes are deliberately NOT failures. This tool's verdict is about the SCRUB --
    # whether de-identification damaged the packet. A section that came in under the
    # prompt's minimum is a defect in the BUILD which the scrub then faithfully preserved,
    # and failing the scrub for it would make the verdict mean nothing.
    if build_notes:
        print("\nBUILD NOTES -- defects in the packet the scrub correctly did not touch:")
        for n in build_notes:
            print("  - %s" % n)

    print("\n" + "=" * 70)
    if failures:
        print("FAILED -- %d problem(s):\n" % len(failures))
        for f in failures:
            print("  * %s" % f)
        return 1
    print("PASSED -- the packet parses, every section is visible to the harness, every")
    print("quote-body change is declared on its line, and no URLs, company identifiers or")
    print("lookup keys survive. This says nothing about whether the BUILD was sound.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
