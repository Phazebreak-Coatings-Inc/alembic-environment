# Logfire

The template ships with [Logfire](https://logfire.pydantic.dev/) tracing. It sends nothing until `LOGFIRE_TOKEN` is set.

## Setup

Use a write token from the Logfire project your app already sends to. Database traces then sit next to your app traces under their own service name. Export it:

```sh
export LOGFIRE_TOKEN=your-write-token
```

In CI, add `LOGFIRE_TOKEN` as a repository secret. `alembic-cicd.yml` reads it.

Traces are stored in Logfire. Nothing is written to your databases.

## What is traced

- Every `migrations`, `models` and `environments` command
- Every `alembic` run, linked to the command that started it
- Every SQL statement through SQLAlchemy
- Every seed and backfill function

## Settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `LOGFIRE_TOKEN` | unset | Enables sending |
| `LOGFIRE_SERVICE_NAME` | `<root project>-database` | Service name in Logfire |
| `LOGFIRE_ENVIRONMENT` | `ALEMBIC_ENV` | Environment tag |
| `LOGFIRE_CONSOLE` | off | Set to `true` to print spans to the terminal |

## Custom spans

`logfire` is configured before your seeds and backfills run. Use it directly:

```python
import logfire

@seed(["dev"])
def users(session: Session) -> None:
    with logfire.span("insert users"):
        ...
```
