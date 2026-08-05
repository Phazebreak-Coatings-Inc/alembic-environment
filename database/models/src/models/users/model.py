from ..base_model import SQLModelBase
from .base import UsersBase
from abc import ABC
from sqlmodel import SQLModel, Field
from typing import Self


class CreateMixin(SQLModel, ABC):
    created_by: str | None = Field()

    @classmethod
    def create(cls, username: str = "Anonymous", **kwargs) -> Self:
        return cls(created_by=username, **kwargs)


class Users(SQLModelBase, UsersBase, CreateMixin, table=True):
    pass  # add methods here

