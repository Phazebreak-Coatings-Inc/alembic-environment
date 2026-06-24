## Copy the Template

First we'll create a uv workspace.

```sh
uv init
```

Then we'll use ```uvx``` to create copy the directory from remote.

```sh
uvx alembic-environment init . 

```
If the template updates from remote, we can use this command to sync it:

```sh
uvx alembic-environment update
```

This will create two folders: ```./migrations/``` and ```./models/``` as well as ```alembic.ini```.

Run the ```--help``` command on the migrations module to view available commands:

```sh
uv run python -m migrations --help
```

## Create your Models and Migrations

Create your first model at ```./models/src/models/my_model.py```:

```python
from sqlmodel import SQLModel, Field

class MyTable(SQLModel, table=True):
    id: int = Field(primary_key=True, default=1)
```

After creating a model with either SQLModel or SQLAlchemy, make sure to import it at ```./models/src/models/__init__.py```.

```python
from .mymodel import MyTable

__all__ = ["MyTable"]
```

Now, autogenerate a migration:

```sh
uv run python -m migrations migrate
```

Your migration will appear in ```./migrations/src/migrations/versions/```
