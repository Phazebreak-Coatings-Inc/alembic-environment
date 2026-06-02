from sqlmodel import SQLModel
from migrations import APP_METADATA

class MyModel(SQLModel):
    metadata = APP_METADATA
    foo: int = 1
    bar: str = "baz"
