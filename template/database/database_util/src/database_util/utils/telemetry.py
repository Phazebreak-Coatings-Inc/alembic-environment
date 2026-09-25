import functools
import os
from collections.abc import Iterator
from contextlib import contextmanager

import logfire
from logfire.propagate import attach_context, get_context

SERVICE_NAME = "database"
TRACE_ENV_VARS = ("TRACEPARENT", "TRACESTATE")


@functools.cache
def configure_telemetry() -> None:
    """Configure logfire once per process. Sends data only when LOGFIRE_TOKEN is set."""
    logfire.configure(
        service_name=os.environ.get("LOGFIRE_SERVICE_NAME", SERVICE_NAME),
        environment=os.environ.get("LOGFIRE_ENVIRONMENT")
        or os.environ.get("ALEMBIC_ENV"),
        send_to_logfire="if-token-present",
        console=None if "LOGFIRE_CONSOLE" in os.environ else False,
    )
    logfire.instrument_sqlalchemy()


def trace_env() -> dict[str, str]:
    """The current trace context as environment variables for a subprocess."""
    return {k.upper(): v for k, v in get_context().items()}


@contextmanager
def inherited_trace() -> Iterator[None]:
    """Continue a trace started by a parent process."""
    carrier = {k.lower(): os.environ[k] for k in TRACE_ENV_VARS if k in os.environ}
    with attach_context(carrier):
        yield
