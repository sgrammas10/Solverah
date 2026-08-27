"""Pure functions and value objects.  No Flask, no SQLAlchemy, no network.

See docs/ARCHITECTURE.md 2.2.  Anything in here can be called from a test with
no application context, from a Celery worker, or from a notebook, and it will
behave identically.  That is the property that makes the scoring and matching
logic -- the most valuable code in the product -- worth having in one place.

The heavier deterministic ML (resume parsing, culture fit, path scoring) lives
in ``packages/ml`` rather than here, because it is a library the API consumes
rather than a rule the API enforces.  What belongs here is the smaller stuff
that was tangled into handlers: verification-code lifetimes, lockout arithmetic,
the shape of a blank profile.
"""
