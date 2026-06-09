from typing import Optional
import datetime


from pydantic import BaseModel


class UsersValidator(BaseModel):
    user_id: int
    username: str
    email: Optional[str] = None
    password: Optional[str] = None
    join_date: Optional[datetime.date] = None
