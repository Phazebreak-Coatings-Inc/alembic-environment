from typing import TYPE_CHECKING, List, Optional
from sqlmodel import Relationship
from ..base_model import SQLModelBase
from .base import OrdersBase
from .mixin import OrdersMixin

if TYPE_CHECKING:
    from ..users.model import Users


class Orders(OrdersMixin, SQLModelBase, OrdersBase, table=True):
    user: "Users" = Relationship(back_populates="orders")
