from typing import Literal

DEV_ENV = ".env.dev"
STAGING_ENV = ".env.staging"
PROD_ENV = ".env.prod"
ValidDatabaseEnvironments = Literal["dev", "staging", "prod"]
ENVS = ["dev", "staging", "prod"]
