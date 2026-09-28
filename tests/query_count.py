"""Count the SQL statements a block of code sends to the database.

The DB-ledger regression tests use this to pin a fix: an N+1 that comes back
shows up as a count that grows with the number of rows. Compare a small and a
large fixture instead of asserting an exact number where you can, so an
unrelated extra read does not fail a test that is about something else.
psycopg2's executemany is one event here but one round trip per row.
"""

from __future__ import annotations

import contextlib
from typing import Iterator, List

from sqlalchemy import event

from model import db


@contextlib.contextmanager
def count_queries() -> Iterator[List[str]]:
    """Yield a list that collects every statement executed inside the block."""
    statements: List[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = db.engine
    event.listen(engine, "before_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _record)
