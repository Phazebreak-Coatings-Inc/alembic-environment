from migrations import APP_METADATA
from sqlmodel import SQLModel

class MyModel(SQLModel):
    metadata = APP_METADATA
    foo: int = 1
    bar: str = "baz"
