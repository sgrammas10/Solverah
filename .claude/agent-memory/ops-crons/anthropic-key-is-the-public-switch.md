---
name: anthropic-key-is-the-public-switch
description: setting ANTHROPIC_API_KEY in Render turns CompanyLens research on for every signed-in user; blocked_domains unwired; attorney gate unresolved (2026-10-14)
metadata:
  type: project
---

There is no feature flag between "key set" and "public". With `ANTHROPIC_API_KEY` set,
`POST /companies/research` serves any signed-in user, up to 5 new runs a day each.
Unset, the route returns a typed 503 and writes nothing. Review-site collection needs
attorney review before research goes public (decided 2026-10-13). The research client
accepts `blocked_domains`, but as of 2026-10-14 the service never passes it.

**Why:** Sebastian plans to create the key and set it on deploy day, and that same act
makes research public.

**How to apply:** on deploy day, before the key goes into Render, confirm which way it
was decided: keep the key unset until the attorney has reviewed collection, or wire
`blocked_domains` first (matching-model). Measure cost first with a LOCAL run of
`flask companies research`. See [[companies-sweep-cron]].
