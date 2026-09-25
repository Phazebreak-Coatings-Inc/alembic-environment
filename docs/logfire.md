# Logfire

The template traces to [Logfire](https://logfire.pydantic.dev/) using the same setup as `fastapi-environment`. It sends nothing until a token is found.

Traces are stored in Logfire. Nothing is written to your databases.

## Project

`environments up prod` creates one Logfire project and a write token with Terraform. The project is named `<root project>_database`. Staging and prod share it. They are split by the `deployment.environment` attribute.

Terraform needs a Logfire API key with project and token management scopes:

```sh
export LOGFIRE_API_KEY=your-api-key
```

## Token

Staging and prod read the token from the `logfire_token` Terraform output. Dev and the migrations database need it set by hand:

```sh
export LOGFIRE_TOKEN=your-write-token
```

In CI, add `LOGFIRE_TOKEN` as a repository secret. `alembic-cicd.yml` reads it.

If staging or prod has no token, the CLI prints a warning.

## What is traced

- Every `migrations`, `models` and `environments` command
- Every step those commands run
- Every `alembic` run, linked to the command that started it
- Every SQL statement through SQLAlchemy
- Every seed and backfill function
- Python `logging` records

## Settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `LOGFIRE_TOKEN` | Terraform output in staging and prod | Enables sending |
| `LOGFIRE_API_KEY` | unset | Lets Terraform create the project and token |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset | Sends to another OTLP backend |
| `OTEL_EXPORTER_OTLP_HEADERS` | unset | Headers for that backend |

## Custom spans

`step` prints a message and opens a span:

```python
from database_util.utils import step

with step("Loading users...", "load users", count=10):
    ...
```

`logfire` is configured before seeds and backfills run. Use it directly:

```python
import logfire

@seed(["dev"])
def users(session: Session) -> None:
    with logfire.span("insert users"):
        ...
```
