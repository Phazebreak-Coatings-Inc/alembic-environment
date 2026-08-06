"""Backfill for revision 16a29e90ac0e."""

from sqlmodel import Session

from database_core import backfill


@backfill("16a29e90ac0e")
def backfill_16a29e90ac0e(session: Session) -> None:
    ...
