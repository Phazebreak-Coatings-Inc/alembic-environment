from sqlmodel import Session
from database_core import seed

@seed(['dev'])
def foobar(session: Session) -> None:
    ...
