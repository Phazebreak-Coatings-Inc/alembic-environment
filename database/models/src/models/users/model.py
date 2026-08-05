from typing import TYPE_CHECKING, List, Optional
from sqlmodel import Relationship
from ..base_model import SQLModelBase
from .base import UsersBase
from .mixin import UsersMixin

if TYPE_CHECKING:
    from ..orders.model import Orders


class Users(UsersMixin, SQLModelBase, UsersBase, table=True):
    orders: list["Orders"] = Relationship(back_populates="user")
