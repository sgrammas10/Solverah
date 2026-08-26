"""The Solverah API package.

``create_app`` is exposed lazily.  A plain ``from .factory import create_app``
here would mean that importing *anything* under ``solverah`` -- ``solverah.config``
in a settings test, ``solverah.errors`` in an error-shape test -- pulled in
Flask, SQLAlchemy, the models, and the whole blueprint registry as a side
effect.  That is the failure mode this package exists to remove, so it is not
reintroduced one level up.
"""

__all__ = ["create_app"]


def __getattr__(name: str):
    if name == "create_app":
        from .factory import create_app

        return create_app
    raise AttributeError("module %r has no attribute %r" % (__name__, name))
