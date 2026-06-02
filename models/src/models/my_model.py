from sqlmodel import SQLModel, Field
from migrations import APP_METADATA


class MyModel(SQLModel, table=True):
    metadata = APP_METADATA
    id: int | None = Field(default=None, primary_key=True)
    foo: int = 1
    bar: str = "baz"
