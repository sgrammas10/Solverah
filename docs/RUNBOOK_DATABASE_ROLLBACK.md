# Runbook — Database rollback

**Status:** Path A rehearsed · Path C unrehearsed · **Owner:** Engineering · **Last revised:** 2026-08-27

Phase 0 and Phase 1 were reversible by redeploying the previous image. Phase 2 is the
first phase where that stops being true: once a migration has rewritten rows, the old
code no longer fits the data underneath it, and the only way back is the database.

This runbook is that way back. Read it *before* running a Phase 2 migration, not during
the incident — Path C below takes longer to think through than to execute.

---

## 1. The three paths, fastest first

| | Path | Restores | Connection string | Wall clock at today's volume |
|---|---|---|---|---|
| **A** | Pre-migration snapshot you took yourself | Whatever you captured, in place | **Unchanged** | ~1 min |
| **B** | Render logical backup ("export") | Last export, ≤ 7 days old | **Unchanged** | ~5–10 min |
| **C** | Render point-in-time recovery | Any moment in the PITR window | **NEW — every service must be repointed** | Tens of minutes |

**Path A is the Phase 2 rollback.** B and C are what you use when A is unavailable or
when the damage is discovered days later. The ranking is not about restore speed — at
10 MB every option moves the data in seconds — it is about the connection string, which
is covered in §4 and is the part that actually costs time.

---

## 2. Path A — the pre-migration snapshot *(do this every Phase 2 migration)*

### Take it

```sh
make db-snapshot                      # writes ./backups/solverah-<UTC timestamp>.dump
```

or directly:

```sh
pg_dump "$DATABASE_URL" -Fc --no-owner --no-acl -f solverah-pre-migration.dump
```

Measured against production on 2026-08-27, from a developer machine to Render's Oregon
region: **16.5 s**, producing a 68 KB compressed archive from a 10 MB database. There
is no meaningful reason to skip this step.

The application role (`solverah_postgres_user`) has the rights to dump the entire
database — verified, not assumed.

### Put it back

```sh
make db-restore SNAPSHOT=backups/solverah-<timestamp>.dump CONFIRM=yes
```

or directly — note `--clean --if-exists`, which is what makes this an in-place rollback
rather than a merge into a schema that still has the migration's changes in it:

```sh
pg_restore --clean --if-exists --no-owner --no-acl -d "$DATABASE_URL" solverah-pre-migration.dump
```

Then redeploy the API on the pre-migration commit. `DATABASE_URL` never changed, so
nothing else needs touching.

### Rehearsed, not assumed

This path was walked end to end on 2026-08-27 against `pgvector/pgvector:pg18` holding
the real production schema: snapshot, then a deliberately destructive change — half the
`audit_log` rows deleted *and* `user.reset_token` dropped — then `pg_restore --clean`
in place. Row counts and the dropped column both came back, at both volumes.

| Database size | Rows | Snapshot | Dump | **In-place restore** |
|---|---|---|---|---|
| 10 MB — production today | 935 audit · 6 users · 21 companies | 68 KB | 0.9 s | **1.4 s** |
| 424 MB | 2.0 M audit · 50 k users | 19 MB | 6.2 s | **15.0 s** |

The 424 MB row answers "when does this stop being cheap?" — and the answer is not soon.
The restore stays under a minute well past any volume Phase 2 will see.

Both rows use synthetic data generated at matching volume against the real production
schema, not a copy of production data. The 16.5 s network dump in the previous section
*is* production.

---

## 3. Path B — Render's logical backup

Render takes its own logical backups and **retains them for seven days regardless of
workspace plan**. Use this when no Path A snapshot exists.

1. Render Dashboard → the database → **Recovery** page.
2. The exports table lists archives as `.dir.tar.gz`. Download the one you want.
   (**Create export** makes a fresh one; only one export can be running at a time.)
3. Unpack and restore — it is directory format, so `pg_restore`, not `psql`:

```sh
tar -xzf <export>.dir.tar.gz
pg_restore --clean --if-exists --no-owner --no-acl -d "$DATABASE_URL" <unpacked-dir>/
```

Render's own warning applies and is not boilerplate: *do not restore into a database
that contains important data in the same schema as the export.* `--clean` drops the
objects it is about to recreate.

Slower than Path A only because of the download and unpack; the restore itself is the
same operation with the same timings.

---

## 4. Path C — point-in-time recovery, and the trap in it

Render runs continuous WAL archiving — confirmed on the live instance, which reports
`archive_mode = on` with a pgBackRest `archive_command`. So PITR is genuinely available,
not just advertised.

1. Dashboard → the database → **Recovery** → **Point-in-Time Recovery** → **Restore
   Database**.
2. Name the recovery instance, pick the timestamp — it **cannot be within 10 minutes of
   now**, so a mistake made five minutes ago is not yet recoverable this way. Path A is.
3. **Copy Existing Settings** → yes, unless you deliberately want a different instance
   type. Then **Start Recovery**.
4. Status goes *Recovery In Progress* → *Creating* → *Available*.
5. Verify the recovered data **before** cutting over.
6. Repoint every service at the new instance, redeploy, confirm, and only then suspend
   or delete the original.

### The trap

**Render PITR does not restore in place. It creates a new database instance with a new
name and new credentials.** Nothing is repointed for you.

That makes step 6 — not the recovery — the expensive part, and it is the step most
likely to be got wrong under pressure. Before you need it, know exactly what holds a
copy of `DATABASE_URL`:

- the Render API service's environment (`DATABASE_URL`),
- any Render cron/worker services,
- local `.env` files,
- anything in CI or in a teammate's shell.

A rollback that restores correct data while one worker keeps writing to the old instance
is worse than no rollback, because now there are two divergent databases and no record
of which rows went where.

**Recovery window: 7 days.** Confirmed on the Recovery page, 2026-08-27 — the workspace
is on Pro or higher (Hobby would offer 3). Free instances get no recovery at all.

Two things about that window are easy to misread:

- It is a *rolling* window, not a set of daily snapshots. Any instant within the last
  seven days is a valid recovery target, down to the 10-minute floor above.
- Upgrading a plan does **not** backfill it. If the workspace plan ever changes, the
  longer window starts accruing from that moment, so re-check this line rather than
  assuming seven days survived the change.

---

## 5. Pre-flight, per Phase 2 migration

Phase 2 is expand/contract, one aggregate at a time — the discipline below is what makes
that shape actually reversible rather than just incremental.

- [ ] Take the Path A snapshot. Record the filename in the change notes.
- [ ] Confirm the snapshot is non-empty and restores: `pg_restore --list <file> | head`.
- [ ] Confirm the change is inside the 7-day PITR window (§4) as a second line of
      defence — i.e. that you would notice the damage within a week. A backfill whose
      wrongness only shows up in a monthly report is outside what PITR can save.
- [ ] Expand only — additive DDL, dual-write, backfill, verify. **No destructive step in
      the same deploy as the additive one.** The contract phase is a separate, later
      change, run only once the expand phase has been live and correct.
- [ ] Know which of A/B/C you would use, before starting.

The reason for the third-from-last item is that Path A restores *data*, and a dropped
column is not recovered by a redeploy — it is recovered by a restore, which throws away
every write since the snapshot. Splitting expand from contract keeps almost every
rollback in "redeploy the old image" territory, where no data is lost at all.

---

## 6. What is measured, and what is not

Measured on 2026-08-27 against the live Render instance and a local `pgvector/pgvector:pg18`
container:

- Production reports `PostgreSQL 18.3 (Debian 18.3-1.pgdg12+1)`.
- `pg_dump` of production: 16.5 s, 68 KB, by the application role.
- `pg_restore` timings in §2, from the production schema plus synthetic data at matching
  volume, including a full destroy-and-recover drill at both volumes.
- `archive_mode = on` with a pgBackRest `archive_command`.
- Instance shape: `max_connections = 103`, `shared_buffers = 64 MB`.

Confirmed from the Render dashboard on 2026-08-27:

- PITR window is **7 days** (workspace on Pro or higher).

**Not yet rehearsed:**

- **A real Render PITR has never been triggered.** The steps in §4 come from Render's
  documentation, and Render does not publish a duration, so the "tens of minutes" in §1
  is an estimate rather than a measurement.

  This is deliberately not a blocker. Path C is the backstop, not the rollback — Path A
  is the rollback, and it *has* been walked end to end. Path C only matters when the
  snapshot is unusable or the damage surfaces days later. Worth one drill before you are
  depending on it: recover to an hour ago, confirm the instance comes up with plausible
  data, delete it, and write the measured duration into §1. Note that the drill
  provisions a real billable instance that runs until deleted.
