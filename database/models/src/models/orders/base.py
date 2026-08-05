from typing import Optional
import datetime
from sqlalchemy import (
    Column,
    Date,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    text,
)
from sqlmodel import Field, Relationship, SQLModel


from sqlmodel import SQLModel, Field


class OrdersBase(SQLModel):
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"], ["users.user_id"], name="orders_user_id_fkey"
        ),
        PrimaryKeyConstraint("order_id", name="orders_pkey"),
    )
    order_id: int = Field(sa_column=Column("order_id", Integer, primary_key=True))
    user_id: int = Field(sa_column=Column("user_id", Integer, nullable=False))
    title: Optional[str] = Field(default=None, sa_column=Column("title", String(500)))
    description: Optional[str] = Field(
        default=None, sa_column=Column("description", String(2000))
    )
