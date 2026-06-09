from typing import Optional
import datetime
from sqlalchemy import (
    Column,
    Date,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    text,
)
from sqlmodel import Field, SQLModel


from sqlmodel import SQLModel, Field, Relationship


class UsersBase(SQLModel):
    __table_args__ = (
        PrimaryKeyConstraint("user_id", name="users_pkey"),
        UniqueConstraint("username", name="users_username_key"),
    )
    user_id: int = Field(sa_column=Column("user_id", Integer, primary_key=True))
    username: str = Field(sa_column=Column("username", String(50), nullable=False))
    email: Optional[str] = Field(default=None, sa_column=Column("email", String(100)))
    password: Optional[str] = Field(
        default=None, sa_column=Column("password", String(100))
    )
    join_date: Optional[datetime.date] = Field(
        default=None,
        sa_column=Column("join_date", Date, server_default=text("CURRENT_TIMESTAMP")),
    )
