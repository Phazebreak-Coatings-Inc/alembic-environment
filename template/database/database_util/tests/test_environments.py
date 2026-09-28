import json
import subprocess

import pytest
from copier_template import util
from database_util import utils
from database_util.utils import (
    DatabaseSettings,
    DevEnvironment,
    MigrationEnvironment,
    ProdEnvironment,
    StagingEnvironment,
    get_database_environment,
    get_database_setting,
)

OUTPUTS = {
    "database_host": {"value": "db.example.com", "sensitive": False, "type": "string"},
    "database_port": {"value": 25060, "sensitive": False, "type": "number"},
    "prod_name": {"value": "prod", "sensitive": False, "type": "string"},
    "prod_username": {"value": "prod_user", "sensitive": False, "type": "string"},
    "prod_password": {"value": "p@ss/word", "sensitive": True, "type": "string"},
    "staging_name": {"value": "staging", "sensitive": False, "type": "string"},
    "staging_username": {"value": "staging_user", "sensitive": False, "type": "string"},
    "staging_password": {"value": "s3cret", "sensitive": True, "type": "string"},
    "admin_username": {"value": "doadmin", "sensitive": False, "type": "string"},
    "admin_password": {"value": "admin", "sensitive": True, "type": "string"},
}

CLI_ENV = ("DO_TOKEN", "TF_VAR_DO_TOKEN", "LOGFIRE_API_KEY", "TF_WORKSPACE")


@pytest.fixture
def terraform(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake(cmd, **kwargs):
        calls.append((cmd, kwargs))
        stdout = json.dumps(OUTPUTS) if cmd.startswith("terraform output") else ""
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(util, "sh", fake)
    for name in CLI_ENV:
        monkeypatch.delenv(name, raising=False)
    return calls


@pytest.fixture
def prod(tmp_path, terraform):
    return ProdEnvironment(tmp_path)


class TestDatabaseSettings:
    def test_reads_database_env_vars(self, monkeypatch):
        monkeypatch.setenv("DATABASE_HOST", "runtime.example.com")
        monkeypatch.setenv("DATABASE_PORT", "6543")
        monkeypatch.setenv("DATABASE_NAME", "app")
        monkeypatch.setenv("DATABASE_USERNAME", "app_user")
        monkeypatch.setenv("DATABASE_PASSWORD", "pw")
        s = DatabaseSettings()
        assert (
            s.database_url
            == "postgresql+psycopg://app_user:pw@runtime.example.com:6543/app"
        )

    def test_url_escapes_password(self):
        s = DatabaseSettings(
            database_host="h",
            database_port=1,
            database_name="d",
            database_username="u",
            database_password="p@ss/word",
        )
        assert s.database_url == "postgresql+psycopg://u:p%40ss%2Fword@h:1/d"


class TestLookup:
    def test_environment_types(self):
        assert isinstance(get_database_environment("dev"), DevEnvironment)
        assert isinstance(get_database_environment("mig"), MigrationEnvironment)
        assert isinstance(get_database_environment("staging"), StagingEnvironment)
        assert isinstance(get_database_environment("prod"), ProdEnvironment)

    def test_setting_is_runtime_settings(self):
        s = get_database_setting("dev")
        assert type(s) is DatabaseSettings
        assert s.database_name == "dev_db"

    def test_rejects_unknown_env(self):
        with pytest.raises(ValueError):
            get_database_environment("qa")


class TestTerraformedEnvironment:
    def test_settings_from_outputs(self, prod):
        s = prod.settings
        assert type(s) is DatabaseSettings
        assert (s.database_host, s.database_port) == ("db.example.com", 25060)
        assert (s.database_name, s.database_username) == ("prod", "prod_user")
        assert s.database_password == "p@ss/word"

    def test_staging_uses_staging_outputs(self, tmp_path, terraform):
        s = StagingEnvironment(tmp_path).settings
        assert (s.database_name, s.database_username, s.database_password) == (
            "staging",
            "staging_user",
            "s3cret",
        )

    def test_admin_settings(self, prod):
        a = prod.admin_settings
        assert (a.database_username, a.database_password) == ("doadmin", "admin")
        assert a.database_name == "prod"

    def test_outputs_read_once(self, prod, terraform):
        assert prod.settings.database_name == prod.admin_settings.database_name
        outputs = [c for c, _ in terraform if c.startswith("terraform output")]
        assert len(outputs) == 1

    def test_terraform_env(self, monkeypatch, prod, terraform):
        monkeypatch.setenv("DO_TOKEN", "dop_x")
        monkeypatch.setenv("TF_WORKSPACE", "ws")
        prod.get_output("database_host")
        _, kwargs = terraform[0]
        assert kwargs["cwd"] == prod.terraform_dir
        env = kwargs["env"]
        assert env["TF_VAR_do_token"] == "dop_x"
        assert env["TF_WORKSPACE"] == "ws"
        assert env["TF_VAR_project_name"] == utils.read_project_name()

    def test_apply_requires_credentials(self, prod, terraform):
        with pytest.raises(ValueError, match="DO_TOKEN, LOGFIRE_API_KEY"):
            prod.apply()
        assert terraform == []

    def test_apply_runs_terraform_and_resets(self, monkeypatch, prod, terraform):
        monkeypatch.setenv("DO_TOKEN", "dop_x")
        monkeypatch.setenv("LOGFIRE_API_KEY", "lf")
        assert prod.settings.database_name == "prod"
        prod.apply()
        cmds = [c for c, _ in terraform]
        assert "terraform init -upgrade" in cmds
        assert "terraform apply -auto-approve" in cmds
        assert prod.settings.database_name == "prod"
        assert sum(c.startswith("terraform output") for c in cmds) == 1
        assert sum(c.startswith("terraform output") for c, _ in terraform) == 2


class TestTerraformedUp:
    @pytest.fixture
    def calls(self, monkeypatch, prod):
        calls: list[str] = []
        monkeypatch.setattr(prod, "apply", lambda: calls.append("apply"))
        monkeypatch.setattr(
            utils, "run_steps", lambda fns, label=None: calls.append("steps")
        )
        return calls

    def test_applies_when_already_reachable(self, monkeypatch, prod, calls):
        monkeypatch.setattr(prod, "ping", lambda **kw: calls.append("ping"))
        prod.up()
        assert calls == ["ping", "apply"]

    def test_runs_steps_when_first_created(self, monkeypatch, prod, calls):
        pings: list[dict] = []

        def ping(**kw):
            pings.append(kw)
            if len(pings) == 1:
                raise RuntimeError("unreachable")

        monkeypatch.setattr(prod, "ping", ping)
        prod.up()
        assert calls == ["apply", "steps"]
        assert pings[1]["attempts"] == 60

    def test_startup_forces_steps(self, monkeypatch, prod, calls):
        monkeypatch.setattr(prod, "ping", lambda **kw: calls.append("ping"))
        prod.up(startup=True)
        assert calls == ["ping", "apply", "steps"]
