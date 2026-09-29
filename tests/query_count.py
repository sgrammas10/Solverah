"""Count the SQL statements a block of code sends to the database.

The DB-ledger regression tests use this to pin a fix: an N+1 that comes back
shows up as a count that grows with the number of rows. Compare a small and a
large fixture instead of asserting an exact number where you can, so an
unrelated extra read does not fail a test that is about something else.
psycopg2's executemany is one event here but one round trip per row; use
:func:`count_round_trips` when that is the shape under test.
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


@contextlib.contextmanager
def count_round_trips() -> Iterator[List[str]]:
    """:func:`count_queries`, except an executemany counts once per parameter set.

    psycopg2's ``executemany`` is one ``before_cursor_execute`` event and one
    round trip per row, so :func:`count_queries` would report a per-row loop
    sent that way as one statement. Only a *list* of parameter sets is a real
    executemany: an "insertmanyvalues" batch also arrives flagged
    ``executemany`` but with one dict, and is one round trip.
    """
    trips: List[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        many = executemany and isinstance(parameters, (list, tuple))
        trips.extend([statement] * (len(parameters) if many else 1))

    engine = db.engine
    event.listen(engine, "before_cursor_execute", _record)
    try:
        yield trips
    finally:
        event.remove(engine, "before_cursor_execute", _record)
