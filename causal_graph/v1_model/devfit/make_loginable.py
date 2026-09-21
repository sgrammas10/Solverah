"""Make ONE synthetic user able to sign in, so a fit can be looked at in the app.

    python -m causal_graph.v1_model.devfit.make_loginable \
        --email synth-00032@synthetic.solverah.invalid --password <anything>

The seeder writes synthetic users with a placeholder password hash and no confirmed
email, so none of them can log in -- deliberately, they are rows, not accounts. This
turns one into an account: a real bcrypt hash (the app's own hasher), a confirmed
email, an active status. Nothing else about the user changes; their core sitting and
environment report are what the Situation Report will rank.

Guarded like everything in this package: it refuses any database but a local
`solverah_modeldev*`, and it refuses any email outside the synthetic domain -- it must
never be a way to set a password on a real person's account.
"""
from __future__ import annotations

import argparse
import datetime
import os

from .guard import add_database_argument, require_database_url
from .seed_synthetic import SYNTHETIC_EMAIL_DOMAIN


class NotSyntheticError(RuntimeError):
    """The email is not a synthetic user's. Never downgraded to a warning."""


def assert_synthetic_email(email: str) -> str:
    if not isinstance(email, str) or not email.strip().lower().endswith(SYNTHETIC_EMAIL_DOMAIN):
        raise NotSyntheticError(
            "%r is not a synthetic user (emails must end %s) -- this script sets a "
            "password, and may only ever do that to a row the seeder made"
            % (email, SYNTHETIC_EMAIL_DOMAIN)
        )
    return email.strip()


def make_loginable(db, user, password: str, hash_password) -> None:
    """Give `user` a real password hash, a confirmed email and an active status.
    Does NOT commit -- the caller owns the transaction, same as the stores."""
    from model import USER_STATUSES

    assert_synthetic_email(user.email)
    if not password:
        raise ValueError("an empty password would make the account unusable, not safe")
    hashed = hash_password(password)
    user.password_hash = hashed.decode("utf-8") if isinstance(hashed, bytes) else hashed
    if user.email_confirmed_at is None:
        user.email_confirmed_at = datetime.datetime.now(datetime.timezone.utc)
    if "active" in USER_STATUSES:
        user.status = "active"
    user.failed_login_count = 0
    user.locked_until = None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_database_argument(parser)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args(argv)

    url = require_database_url(args.database_url)
    email = assert_synthetic_email(args.email)
    os.environ["DATABASE_URL"] = url

    from app import app
    from model import User, db
    from solverah.extensions import bcrypt

    with app.app_context():
        user = User.query.filter(User.email == email).first()
        if user is None:
            raise SystemExit("no user %s in this database" % email)
        make_loginable(db, user, args.password, bcrypt.generate_password_hash)
        db.session.commit()
    print("ok: %s can now sign in (local model-dev database only)" % email)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
