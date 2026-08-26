"""v1 blueprint registry.

Every handler in the application is reachable at two paths during the Phase 1
cutover: the canonical ``/api/v1/...`` and the legacy ``/api/...`` the deployed
frontend still calls.  Only one of them is declared here.  Blueprints below
carry **prefix-free** rules -- ``/login``, not ``/api/login`` -- and
``register_v1_blueprints`` mounts the whole set under ``/api/v1``.  The factory
then calls :func:`solverah.factory.register_legacy_aliases`, which adds the
unversioned rule for each one against the same endpoint.

That is why Phase 1a adds *only* the prefix and renames nothing: a rule declared
as ``/profile/career-status`` becomes ``/api/v1/profile/career-status`` and
``/api/profile/career-status``, and the two stay in lockstep by construction.
The Part 5.2 renaming (``/me/career-status``, the collapse of five assessment
submit handlers into one, cursor pagination) is Phase 1b, and it is a separate
change precisely because it is the part that alters request and response shapes.

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

from .account import account_bp
from .assessments import assessments_bp
from .auth import auth_bp
from .companies import companies_bp
from .intake import intake_bp
from .intelligence import intelligence_bp
from .profiles import profiles_bp

__all__ = ["BLUEPRINTS", "register_v1_blueprints"]

#: Every v1 blueprint, in document order.  Grows one entry per migrated
#: resource; see the module docstring.
BLUEPRINTS: Tuple[Blueprint, ...] = (
    auth_bp,
    profiles_bp,
    intake_bp,
    assessments_bp,
    companies_bp,
    intelligence_bp,
    account_bp,
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
