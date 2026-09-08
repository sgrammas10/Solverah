ISOLATED BUILD ENVIRONMENT — connect THIS folder, not the repo.

Contents are deliberately minimal:
   BUILD_BRIEF.md                              what the builder reads
   Company_Culture_Evidence_Collector_v*.md    the prompt it runs (exactly one version present -- whichever it is, is the current one)
   packets/                                    where the output lands

HOW TO USE
  1. Open a chat OUTSIDE the Solverah IP Planner project. A new chat inside the project
     still inherits the project's custom instructions, knowledge docs and memory.
  2. Connect ONLY this folder.
  3. Say: Read BUILD_BRIEF.md and build P-01.
  4. When it finishes, copy packets/P-0X_* back into ground_truth/packets/ in the repo.

BEFORE EACH BUILD ROUND
  Re-copy the newest collector prompt into this folder and DELETE the older one. A stale
  copy here is the obvious failure mode of this setup — it would silently build against a
  superseded version. Only one v*.md file should ever be present.
