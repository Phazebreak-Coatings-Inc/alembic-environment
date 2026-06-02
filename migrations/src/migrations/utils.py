from sqlalchemy import MetaData, Engine
from pydantic_settings import BaseSettings

APP_METADATA = MetaData()

class BaseDatabaseSettings(BaseSettings):
    database_port: str
    database_username: str
    database_password: str

    @property
    def database_url(self) -> str:
        return ""

    @property
    def engine(self):
        return Engine()

class DevDatabaseSettings():
    ...

class StagingDatabaseSettings():
    ...

class ProdDatabaseSettings():
    ...
