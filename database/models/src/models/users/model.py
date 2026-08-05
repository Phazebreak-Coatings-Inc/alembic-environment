from ..base_model import SQLModelBase
from .base import UsersBase

class Users(SQLModelBase, UsersBase, table=True):
    pass  # add methods here

