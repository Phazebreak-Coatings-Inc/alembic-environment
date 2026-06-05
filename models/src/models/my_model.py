from sqlmodel import SQLModel, Field

class MyModel(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    foo: int = 1
    bar: str = "baz"
