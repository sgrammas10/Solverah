"""Flask extension singletons, constructed unbound and bound in ``create_app()``.

Before Phase 1 every extension was constructed against the app at ``app.py``
module scope -- ``Bcrypt(app)``, ``JWTManager(app)``, ``Migrate(app, db)``,
``init_rate_limiter(app)``.  Two things fall out of that:

  * There is exactly one app, created at import.  A test cannot build a second
    one with different configuration, and importing anything from ``app.py``
    runs the whole boot sequence as a side effect.
  * A route in another module cannot reach ``limiter`` or ``bcrypt`` without
    importing ``app``, which imports everything.  That is the circular-import
    wall that kept all 38 handlers in one file.

Constructing them here unbound and calling ``init_app`` in the factory breaks
both.  A blueprint module imports ``limiter`` from this module and decorates
freely; ``create_app()`` decides when it is attached and to which app.

``db`` is re-exported rather than declared here: it is still defined in
``model.py`` alongside the models, and moving it is Phase 2's job (splitting
``model.py`` into ``models/`` one aggregate at a time).  Importing it from this
module means the rest of the package already has the right import path when
that move happens.
"""

from __future__ import annotations

from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate

from model import db  # noqa: F401  -- re-exported; see the module docstring
from security import DEFAULT_LIMITS

__all__ = ["bcrypt", "db", "jwt", "limiter", "migrate"]

bcrypt = Bcrypt()
jwt = JWTManager()
migrate = Migrate()

#: Rate limiter.  Storage is resolved and attached by
#: :func:`security.init_rate_limiter` during ``create_app()`` -- constructing it
#: without a ``storage_uri`` here keeps the "which backend?" decision, and the
#: production warning that goes with it, in one place.
limiter = Limiter(get_remote_address, default_limits=DEFAULT_LIMITS)
