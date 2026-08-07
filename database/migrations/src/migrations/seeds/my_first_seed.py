from models import *
from sqlmodel import Session
from database_core import seed

@seed(['dev'])
def my_first_seed(session: Session) -> None:
    ...
