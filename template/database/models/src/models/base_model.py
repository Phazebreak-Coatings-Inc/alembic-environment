from abc import ABC

from sqlmodel import SQLModel


class SQLModelBase(SQLModel, ABC): ...
