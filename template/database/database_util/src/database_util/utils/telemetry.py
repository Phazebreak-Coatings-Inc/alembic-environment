import contextlib
import logging
import os
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager

import inflection
import logfire
import typer
from logfire.propagate import attach_context, get_context
from pydantic_settings import BaseSettings, SettingsConfigDict

from .environments import (
    DatabaseEnvironment,
    TerraformOutputError,
    alembic_env,
    prod_settings,
)
from .paths import ROOT_PYPROJECT

TRACE_ENV_VARS = ("TRACEPARENT", "TRACESTATE")
DEPLOYED_ENVS = ("staging", "prod")

logger = logging.getLogger("alembic-environment")

_TELEMETRY_CONFIGURED = False


def read_project_name() -> str:
    try:
        name = tomllib.loads(ROOT_PYPROJECT.read_text())["project"]["name"]
    except OSError, KeyError, tomllib.TOMLDecodeError:
        return "database"
    return f"{inflection.underscore(name.replace('-', '_'))}_database"


class TelemetrySettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    alembic_env: DatabaseEnvironment = alembic_env
    logfire_token: str = ""
    otel_exporter_otlp_endpoint: str = ""
    otel_exporter_otlp_headers: str = ""

    @property
    def telemetry_enabled(self) -> bool:
        return bool(self.logfire_token or self.otel_exporter_otlp_endpoint)

    def resolve_token(self) -> None:
        if self.logfire_token or self.alembic_env not in DEPLOYED_ENVS:
            return
        with contextlib.suppress(TerraformOutputError, FileNotFoundError):
            self.logfire_token = str(prod_settings.get_output("logfire_token"))

    def setup_telemetry(self, service_name: str | None = None) -> bool:
        global _TELEMETRY_CONFIGURED
        if _TELEMETRY_CONFIGURED:
            return self.telemetry_enabled
        self.resolve_token()
        if self.otel_exporter_otlp_endpoint:
            os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = self.otel_exporter_otlp_endpoint
        if self.otel_exporter_otlp_headers:
            os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = self.otel_exporter_otlp_headers
        logfire.configure(
            service_name=service_name or read_project_name(),
            environment=self.alembic_env,
            token=self.logfire_token or None,
            send_to_logfire="if-token-present" if self.telemetry_enabled else False,
            console=False,
        )
        logfire.instrument_sqlalchemy()
        logging.getLogger().addHandler(logfire.LogfireLoggingHandler())
        _TELEMETRY_CONFIGURED = True
        self.check_telemetry()
        return self.telemetry_enabled

    def check_telemetry(self) -> None:
        if self.telemetry_enabled or self.alembic_env not in DEPLOYED_ENVS:
            return
        msg = (
            f"env={self.alembic_env} but telemetry is unconfigured. "
            "Set LOGFIRE_TOKEN or OTEL_EXPORTER_OTLP_ENDPOINT"
        )
        logger.warning(msg)
        typer.secho(msg, fg=typer.colors.YELLOW, err=True)


def setup_telemetry() -> bool:
    return TelemetrySettings().setup_telemetry()


@contextmanager
def step(message: str, name: str, **attrs) -> Iterator[None]:
    typer.secho(message, fg=typer.colors.YELLOW)
    with logfire.span(name, **attrs):
        yield


def trace_env() -> dict[str, str]:
    """The current trace context as environment variables for a subprocess."""
    return {k.upper(): v for k, v in get_context().items()}


@contextmanager
def inherited_trace() -> Iterator[None]:
    """Continue a trace started by a parent process."""
    carrier = {k.lower(): os.environ[k] for k in TRACE_ENV_VARS if k in os.environ}
    with attach_context(carrier):
        yield
