from models import *
from sqlmodel import Session
from migrations import seed, dev

@seed(dev)
def my_seed(session: Session) -> None:
    ...
