from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from typing import ClassVar
from itertools import chain
from sqlmodel import SQLModel
from jinja2 import meta

TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent / "templates"
if not TEMPLATES_DIR.exists():
    raise FileNotFoundError(f"Missing templates dir at {TEMPLATES_DIR}")

JINJA_ENV = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    trim_blocks=True,
    lstrip_blocks=True,
)

class _Fuzz:
    def __init__(self, name: str = "fuzz"):
        self._name = name

    def __str__(self) -> str:
        return self._name

    def __getattr__(self, item: str) -> "_Fuzz":
        if item.startswith("_"):
            raise AttributeError(item)
        return _Fuzz(f"{item}_val")

    def __getitem__(self, key) -> "_Fuzz":
        return _Fuzz(f"{self._name}_{key}")

    def __iter__(self):
        return iter([_Fuzz(f"{self._name}_{i}") for i in range(2)])


TemplatesRegistryType = dict[str, Path]


class TemplatesRegistry:
    __env__: ClassVar[Environment] = JINJA_ENV
    __opts__: ClassVar[TemplatesRegistryType] = {}

    def __init_subclass__(cls):
        files = chain(
            TEMPLATES_DIR.glob("*.py.j2"),
            TEMPLATES_DIR.glob("*.py.jinja"),
        )
        for f in files:
            print(f"Registered model template at {f}")
            name = f.name.removesuffix(".py.j2").removesuffix(
                ".py.jinja"
            )
            cls.__opts__[name] = f

    @classmethod
    def get_options(cls) -> TemplatesRegistryType:
        return cls.__opts__

    @classmethod
    def validate_option(cls, template: str) -> Path:
        if template not in (opts := cls.get_options()):
            raise ValueError(
                f"'{template}' is not the name of a valid template, choose from {list(opts.keys())} instead"
            )
        return opts[template]

    @classmethod
    def _fuzz_context(cls, template: str) -> dict:
        src = cls.validate_option(template).read_text(encoding="utf-8")
        vars_ = meta.find_undeclared_variables(cls.__env__.parse(src))
        return {v: _Fuzz(v) for v in vars_}

    @classmethod
    def validate_templates(cls) -> dict[str, str | None]:
        results: dict[str, str | None] = {}
        for name in cls.get_options():
            try:
                cls.render(name, cls._fuzz_context(name), validate=True)
                results[name] = None
            except Exception as e:
                results[name] = repr(e)
        return results

    @classmethod
    def render(cls, template: str, context: dict, *, validate: bool = False) -> str:
        path = cls.validate_option(template)
        rendered = cls.__env__.get_template(path.name).render(**context)
        if validate:
            cls._check_runs(rendered, template)
        return rendered

    @classmethod
    def _check_runs(cls, rendered: str, template: str) -> dict:
        before = set(SQLModel.metadata.tables)
        namespace: dict = {}
        try:
            exec(compile(rendered, f"<{template}>", "exec"), namespace)
        except Exception as e:
            raise ValueError(f"{template} failed to run: {e!r}") from e
        finally:
            for name in set(SQLModel.metadata.tables) - before:
                SQLModel.metadata.remove(SQLModel.metadata.tables[name])
        return namespace


template_registry = TemplatesRegistry()
template_registry.validate_templates()
