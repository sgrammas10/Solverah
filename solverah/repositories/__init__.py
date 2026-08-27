"""Data access.  Every database query in the application lives under here.

See docs/ARCHITECTURE.md 2.2: services orchestrate repositories, repositories
own ``db.session``, and nothing above this layer writes a query.  Repositories
return ORM entities or plain values -- never Flask objects, never HTTP status
codes.

Transaction boundaries belong to the *service*, not to the repository: a
repository may ``db.session.add`` and ``flush``, but committing is the caller's
decision, because only the caller knows whether the unit of work is finished.
The exception is ``company_repository.upsert_company``, which commits because
it predates this layering and is called from standalone seeding scripts that
have no service above them.
"""
