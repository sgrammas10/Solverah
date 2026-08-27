"""v1 blueprint registry.

Every route in the application is declared here, mounted under ``/api/v1`` by
:func:`register_v1_blueprints`.  Blueprints carry **prefix-free** rules --
``/auth/login``, not ``/api/v1/auth/login`` -- so the version lives in exactly
one place and a future ``/api/v2`` is a second mount rather than a rewrite of
every module.

Phase 1a additionally bound each rule to an unversioned ``/api/...`` alias, on
the *same endpoint*, so the deployed frontend kept working while the versioned
paths became canonical.  That mattered for two reasons worth remembering even
though the aliases are gone: a redirect on a CORS-preflighted POST is not
handled uniformly across browsers, and Flask-Limiter keys its storage on the
endpoint name, so a second *endpoint* would have given every auth limit a second
independent bucket.  Phase 1b cut the frontend over and removed them.

Adding a resource module:

  1. Declare ``foo_bp = Blueprint("foo", __name__)`` with prefix-free rules.
  2. Import it below and add it to ``BLUEPRINTS``.
  3. Its legacy alias and its OpenAPI entry follow automatically.

``BLUEPRINTS`` order is the order operations appear in the generated OpenAPI
document, so it is grouped the way the API reads rather than alphabetically.
"""

from __future__ import annotations

from typing import List, Tuple

from flask import Blueprint, Flask

from .assessments import assessments_bp
from .auth import auth_bp
from .companies import companies_bp
from .intake import intake_bp
from .intelligence import intelligence_bp
from .me import me_bp

__all__ = ["BLUEPRINTS", "register_v1_blueprints"]

#: Every v1 blueprint, in document order.  Grows one entry per migrated
#: resource; see the module docstring.
BLUEPRINTS: Tuple[Blueprint, ...] = (
    auth_bp,
    me_bp,
    intake_bp,
    assessments_bp,
    companies_bp,
    intelligence_bp,
)


def register_v1_blueprints(app: Flask, url_prefix: str = "/api/v1") -> List[str]:
    """Mount every v1 blueprint on *app* under *url_prefix*.

    Args:
        app: The application being built.
        url_prefix: Where the versioned rules live.  Defaults to ``/api/v1``.

    Returns:
        The blueprint names registered, in order -- for logging and for tests
        that assert the registry is complete.
    """
    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint, url_prefix=url_prefix)
    return [blueprint.name for blueprint in BLUEPRINTS]
