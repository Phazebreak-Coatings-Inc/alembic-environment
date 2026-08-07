
from sqlmodel import Session
from database_core import backfill


@backfill("2a7d456bae34")
def backfill_2a7d456bae34(session: Session) -> None:
    print("my first backfill")
    ...
