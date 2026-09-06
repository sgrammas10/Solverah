ISOLATED SCRUB ENVIRONMENT — connect THIS folder, not the repo, and not _build_env.

This is the SECOND pass. A packet is built in _build_env, then de-identified here, in a
different session. The two are deliberately separate — see "Why a separate pass" in the
ruleset. The short version: if a packet were born de-identified, the unscrubbed version
would never exist, nothing could be diffed, and the scrub would be something you trust
rather than something you check.

Contents are deliberately minimal:
   SCRUB_BRIEF.md                 what the scrubber reads and executes
   ANONYMIZATION_RULES_DRAFT.md   the ruleset it applies — the authority, copied in
   packets_raw/                   the operator drops ONE raw packet here
   packets_out/                   where the scrubbed packet and its diff land

HOW TO USE
  1. Open a chat OUTSIDE the Solverah IP Planner project. A new chat inside the project
     still inherits the project's custom instructions, knowledge docs and memory — and
     those carry company names.
  2. Copy exactly ONE raw packet into packets_raw/ — e.g. P-11_packet.txt.
     One. Not the set. See RULE ZERO in the brief.
  3. Connect ONLY this folder.
  4. Say: Read SCRUB_BRIEF.md and scrub P-11.
  5. When it finishes, copy packets_out/P-0X_packet_ANON.txt into
     ground_truth/anonymization/ in the repo, and keep the diff with it.
  6. Empty packets_raw/ before the next run.

BEFORE EACH SCRUB ROUND
  Re-copy the newest ANONYMIZATION_RULES_DRAFT.md from ground_truth/anonymization/ into
  this folder, replacing the copy here. A stale ruleset is the obvious failure mode of
  this setup — R6's scope, R8's execution and the named-clients rule all changed AFTER
  five packets had already been scrubbed, so this is a thing that actually happens.

  The copy here is a copy. If it and the repo's version disagree, the REPO's version is
  the authority and this one is stale — re-copy it rather than reasoning about which is
  right.

WHY THE OUTPUT IS STILL NAMED "_ANON"
  D-10 says say "de-identified", never "anonymized", and the brief follows that in its
  prose. The FILENAME stays `P-0X_packet_ANON.txt` because
  causal_graph/scorer_pipeline.py resolves packets by that exact name. JC-3 settles that
  the scrubbed packet becomes canonical as `P-0X_packet_RATER.txt`; doing that rename is
  a one-line change in scorer_pipeline.py plus a sweep of its consumers, and it has not
  been done. Until it is, emit `_ANON.txt` — a rename that breaks the citation harness
  costs more than the naming inconsistency does.
