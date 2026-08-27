"""Business logic.  Services own the transaction boundary.

See docs/ARCHITECTURE.md 2.2.  A service orchestrates repositories, calls infra
adapters, and decides when a unit of work is complete.  It knows nothing about
HTTP: no ``request``, no ``jsonify``, no status codes.  It raises
:mod:`solverah.errors` types, or returns a result the API layer serialises.

The rule that matters most while Phase 1 is in flight: a service is called from
a blueprint *and* will be called from a Celery worker in Phase 3.  Anything that
reads ``flask.request`` cannot be, which is why request-scoped values (the
client IP, the user agent, the acting user) are passed in as arguments rather
than fetched from the context.

The one deliberate exception is :mod:`solverah.services.audit`, which reads the
request for the IP and user-agent it records.  That is documented in place.
"""
