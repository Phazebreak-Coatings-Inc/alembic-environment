The models package in ```alembic-environment``` has the ability to create multiple useful python objects from sql files in ```./models/sql```.

##Declaring Your Table

First, create a ```user.sql``` file at ```./models/sql``` and declare a table.

```sql
CREATE TABLE users (
    user_id INT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100),
    join_date DATE DEFAULT CURRENT_TIMESTAMP
);
```

You can separate multiple tables either into multiple ```.sql``` files or one large file.

## Generating Your Objects

Next, we'll want to run generate command:

```sh
uv run python -m models g
```

You'll get a message detailing what models were generated in the command line:
```
Applying users.sql
migrations

Rendered 1 model(s) from ['users.sql']:

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


class Users(SQLModel, table=True):
    __table_args__ = (
        PrimaryKeyConstraint("user_id", name="users_pkey"), 
        UniqueConstraint("username", name="users_username_ke
y"),
    )

    user_id: int = Field(sa_column=Column("user_id", Integer
, primary_key=True))
    username: str = Field(sa_column=Column("username", Strin
g(50), nullable=False))
    email: Optional[str] = Field(default=None, sa_column=Col
umn("email", String(100)))
    join_date: Optional[datetime.date] = Field(
        default=None,
        sa_column=Column("join_date", Date, server_default=t
ext("CURRENT_TIMESTAMP")),
    )

```

It will also generate and test a migration for you:

```
INFO  [alembic.autogenerate.compare.tables] Detected added t
able 'users'
Generating C:\Users\miles\PycharmProjects\alembic-environmen
t\migrations\src\migrations\versions\20260609_e2c6363ccfac_a
uto.py ...  done
Running post write hook 'ruff' ...
Found 1 error (1 fixed, 0 remaining).
  done
=================== test session starts =================== 
platform win32 -- Python 3.14.5, pytest-9.0.3, pluggy-1.6.0 
rootdir: C:\Users\miles\PycharmProjects\alembic-environment 
configfile: pyproject.toml
plugins: alembic-0.12.1, typeguard-4.5.2
collected 4 items                                           

migrations\tests\test_migrations.py ....             [100%] 
```

##Using The Generated Objects

The output in ```./models/src/models``` models folder should look like this:

```
|   __init__.py
|   __main__.py
|
+---users
|   |   base.py
|   |   model.py
|   |   typeddict.py
|   |   validator.py
|   |   __init__.py
|   |
|
+---_cli
|   |   app.py
|   |   __init__.py
|   |
|   +---sql
|   |   |   main.py
|   |   |   __init__.py
```

Ignore the ```./models/src/models/_cli``` folder.

You can find the extendable model that you should use in production at ```./models/src/models/users/model.py```:

```python
from .base import UsersBase


class Users(UsersBase, table=True):
    pass  # add methods here
```

It extends the generated model at ```./models/src/models/users/base.py```:

```python
...

class UsersBase(SQLModel):
    __table_args__ = (
        PrimaryKeyConstraint("user_id", name="users_pkey"),
        UniqueConstraint("username", name="users_username_key"),
    )
    user_id: int = Field(sa_column=Column("user_id", Integer, primary_key=True))
    username: str = Field(sa_column=Column("username", String(50), nullable=False))
    email: Optional[str] = Field(default=None, sa_column=Column("email", String(100)))
    join_date: Optional[datetime.date] = Field(
        default=None,
        sa_column=Column("join_date", Date, server_default=text("CURRENT_TIMESTAMP")),
    )
```

This pattern allows us to add convenience methods or mixins to Users while allowing changes to your original SQL tables at ```./models/sql/users.sql```.

It also generates a TypedDict and Pydantic Validator at ```./models/src/models/users/typeddict.py``` and ```./models/src/models/users/validator.py```:

```python
class UsersDict(TypedDict):
    user_id: int
    username: str
    email: NotRequired[Optional[str]]
    join_date: NotRequired[Optional[datetime.date]]
```

```python
class UsersValidator(BaseModel):
    user_id: int
    username: str
    email: Optional[str] = None
    join_date: Optional[datetime.date] = None
```

##Regenerating your SQL Table

Now, let's add the password column to our table:

```sql
CREATE TABLE users (
    user_id INT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100),
    password VARCHAR(100),
    join_date DATE DEFAULT CURRENT_TIMESTAMP
);
```

We can run our generate command again:

```uv run python -m migrations g```

Alembic has detected the change, and is generating a new migration:

```
INFO  [alembic.ddl.postgresql] Detected sequence named 'user
s_user_id_seq' as owned by integer column 'users(user_id)', 
assuming SERIAL and omitting
INFO  [alembic.autogenerate.compare.tables] Detected added c
olumn 'users.password'
Generating C:\Users\miles\PycharmProjects\alembic-environmen
t\migrations\src\migrations\versions\20260609_74412bbb5201_a
uto.py ...  done
Running post write hook 'ruff' ...
Found 1 error (1 fixed, 0 remaining).
  done
```

As you will see, it has also attached it to the generated python objects:

```python
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
```

However, it has not changed our ```model.py```:

```python
from .base import UsersBase


class Users(UsersBase, table=True):
    pass  # add methods here
```

This way, if you change your tables in SQL, you can still keep all the custom logic for your objects!

## Reverse Generation

The generator above goes one way: SQL → python. Sometimes you go the other way and add a column *in python* — for example with a mixin on your ```model.py``` — rather than in ```./models/sql```. Because your ```model.py``` is part of ```SQLModel.metadata```, **Alembic autogenerate picks that column up** and writes a migration for it, even though nothing in ```./models/sql``` ever mentioned it. That column never shows up in the generated ```base.py``` (which only reflects your SQL), so the file you read gives no hint that the live table is wider than your SQL.

Reverse generation reconciles the two. Say you add a ```TimestampMixin``` to ```users/model.py```:

```python
from datetime import datetime

from sqlmodel import Field

from .base import UsersBase


class TimestampMixin:
    created_at: datetime = Field(nullable=True)


class Users(UsersBase, TimestampMixin, table=True):
    pass  # add methods here
```

```created_at``` is now on the ```users``` table as far as Alembic is concerned, but it isn't in ```./models/sql/users.sql``` and so isn't in ```base.py```. Run:

```sh
uv run python -m models rg
```

It diffs the live model columns (what Alembic sees) against the SQL-derived ```base.py``` columns and writes any **injected** columns back into ```model.py```, commented out, as documentation:

```python
from datetime import datetime

from sqlmodel import Field

from .base import UsersBase


class TimestampMixin:
    created_at: datetime = Field(nullable=True)


class Users(UsersBase, TimestampMixin, table=True):
    pass  # add methods here


# >>> reverse-generated (alembic) >>>
# Columns below live on the model -- what Alembic autogenerate / SQLModel.metadata
# sees -- but are NOT declared in ./models/sql. They're injected in python, e.g. via
# a mixin. Shown commented-out, as documentation only; the mixin still owns them.
# created_at: Optional[datetime.datetime] = Field(default=None, sa_column=Column("created_at", DateTime(), nullable=True))  # reverse-generated from mixin
# <<< reverse-generated (alembic) <<<
```

The block is just talk — it's commented out, so it changes nothing at runtime (the mixin still owns the column). It only documents, right in the table file, which columns Alembic picked up that didn't come from your SQL. The block is delimited and rewritten on every run, so ```rg``` is idempotent: re-running refreshes it in place instead of stacking, and it's removed automatically once the column is no longer injected (e.g. you moved it into ```./models/sql```). Use ```-dr```/```--dry-run``` to preview without writing.
