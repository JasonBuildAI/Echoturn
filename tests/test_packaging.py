"""The metadata is a promise too, and nothing executes it.

A console script whose target has been renamed fails at the moment somebody
types it, which is after it has been installed, released and read about. An
extra that exists in `pyproject.toml` but not in the README is an install
instruction nobody can follow. Both are cheap to check and impossible to notice
by reading.
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path

import tomllib

from echoturn.config import DIALS

ROOT = Path(__file__).resolve().parent.parent
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
PYPROJECT = PROJECT["project"]


def test_every_console_script_points_at_something_callable():
    broken = []
    for name, target in PYPROJECT.get("scripts", {}).items():
        module_name, _, attribute = target.partition(":")
        try:
            module = importlib.import_module(module_name)
            function = getattr(module, attribute)
        except (ImportError, AttributeError) as exc:
            broken.append(f"{name} -> {target}: {exc}")
            continue
        if not callable(function):
            broken.append(f"{name} -> {target}: {attribute} is not callable")
    assert broken == []


def test_the_package_declares_at_least_one_console_script():
    """A guard over an empty list passes while checking nothing."""
    assert PYPROJECT.get("scripts")


def test_every_extra_is_named_in_the_readme():
    """An extra nobody is told to install is an extra nobody installs."""
    readme = (ROOT / "README.md").read_text("utf-8")
    missing = [
        extra
        for extra in PYPROJECT.get("optional-dependencies", {})
        if extra != "dev" and f"echoturn[{extra}]" not in readme
    ]
    assert missing == []


def test_the_declared_readme_and_licence_are_files_that_exist():
    for key, name in (("readme", PYPROJECT["readme"]), ("license", "LICENSE")):
        assert (ROOT / name).is_file(), f"{key} names {name}, which is not there"


def test_the_settings_template_names_every_setting_the_code_reads():
    """A setting missing from the template is one nobody knows exists."""
    template = (ROOT / ".env.example").read_text("utf-8")
    read = set()
    for path in (ROOT / "src").rglob("*.py"):
        read.update(
            re.findall(
                r'"(ECHOTURN_[A-Z_]+|OPENAI_API_KEY)"', path.read_text("utf-8")
            )
        )
    # The dial table builds its names from a prefix, so they are not string
    # literals anywhere; the table itself is where they are asked for.
    read.update(dial.env for dial in DIALS)
    assert read, "no settings were found to check"
    assert sorted(name for name in read if name not in template) == []


def test_the_version_is_not_declared_twice():
    """The version lives in the package; a second copy would be a second answer."""
    assert "version" in PYPROJECT.get("dynamic", [])
    assert "version" not in PYPROJECT
    package = (ROOT / "src/echoturn/__init__.py").read_text("utf-8")
    assert re.search(r'__version__ = "\d', package)


def test_the_package_says_it_is_typed():
    """A type checker only reads annotations for a package that claims them."""
    assert (ROOT / "src/echoturn/py.typed").is_file()
