---
name: project-one-open-link-rule
description: 2026-10-14 UNCOMMITTED - one current job per user: create_company_link closes the open link, ix_ucl_one_open_per_user, PATCH /me/company-links/<id>
metadata:
  type: project
---

One open `user_company_link` per user. `create_company_link` sets the prior open link's `ended_on = max(new started_on, its own started_on)` in the same commit; partial unique index `ix_ucl_one_open_per_user` (ORM + migration 20261013_user_company_link edited in place). `end_company_link(db, user_id, link_id, ended_on=)` returns None (404) / raises ValueError (422); route `PATCH /me/company-links/<id>` body `{ended_on}` -> 200 `{link}`.

**Why:** schema-steward F3/F4; nothing wrote ended_on and pulse_store's "by construction" comment was false. Account deletion RETAINS links (auth-accounts ruling).
**How to apply:** tests that build two open links by hand (via ORM) will now hit IntegrityError. Docker Desktop was down once; `docker compose -f infra/docker/compose.yml up -d db` revives 5433. Cluster on solverah_c5: 168 passed.
