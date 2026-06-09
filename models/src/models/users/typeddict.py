from typing import Optional
import datetime


from typing import NotRequired, TypedDict


class UsersDict(TypedDict):
    user_id: int
    username: str
    email: NotRequired[Optional[str]]
    password: NotRequired[Optional[str]]
    join_date: NotRequired[Optional[datetime.date]]
