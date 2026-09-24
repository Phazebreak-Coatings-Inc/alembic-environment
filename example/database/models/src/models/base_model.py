from abc import ABC
from typing import Self

from sqlmodel import Field, SQLModel

class SQLModelBase(SQLModel, ABC): ...
