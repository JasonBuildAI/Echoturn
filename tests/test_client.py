"""The browser client: it parses, it runs, and it keeps its promises.

The client is JavaScript in a Python repository, so the checks have two halves.
The behaviour is tested in Node, next to the modules it is about, and is run
from here as well - a suite that only one of the two test runners knows about is
a suite that stops being run by whoever uses the other one. What is checked here
is the part that is about this repository rather than about the client: that
every module parses, that the routes it calls are the routes the service
serves, and that nothing in it reaches for anything a page is not allowed to
have.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLIENTS = ROOT / "clients"
MODULES = sorted(CLIENTS.glob("*.js"))
ENTRY = CLIENTS / "echoturn-client.js"


def node() -> str:
    """The Node binary, or a skip.

    Skipped rather than failed because the client is optional for a host that
    only wants the Python package. The repository's own CI runs the same tests
    with Node present, so the skip cannot hide a failure there.
    """
    found = shutil.which("node")
    if not found:
        pytest.skip("node is not installed")
    return found


def test_the_client_ships_modules_and_a_worklet():
    names = {path.name for path in MODULES}
    assert "echoturn-client.js" in names
    assert "worklet.js" in names


@pytest.mark.parametrize("path", MODULES, ids=lambda path: path.name)
def test_every_module_parses(path: Path):
    done = subprocess.run(
        [node(), "--check", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr


def test_the_node_suite_passes():
    done = subprocess.run(
        [node(), "--test", "clients/tests/*.test.js"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_routes_the_client_calls_are_the_routes_it_documents():
    """One place per route name: a second one is a second one to keep in step."""
    called = set()
    for path in MODULES:
        called.update(re.findall(r'"(/api/[a-z_]+)"', path.read_text("utf-8")))
    assert called == {"/api/turn", "/api/transcribe"}


def test_the_client_does_not_reach_for_anything_a_page_may_not_have():
    """A user-facing page has no data plane; the client is what a page runs."""
    for path in MODULES:
        text = path.read_text("utf-8")
        for forbidden in ("/admin", "/ops", "/api/admin", "overview", "debug"):
            assert forbidden not in text, f"{path.name} mentions {forbidden}"


def test_the_processor_name_matches_the_file_that_registers_it():
    worklet = (CLIENTS / "worklet.js").read_text("utf-8")
    registered = re.search(r'registerProcessor\("([^"]+)"', worklet)
    assert registered, "the worklet registers no processor"
    mic = (CLIENTS / "mic.js").read_text("utf-8")
    assert f'WORKLET_NAME = "{registered.group(1)}"' in mic


def test_the_entry_point_only_imports_files_that_are_there():
    imports = re.findall(r'from "\./([a-z0-9_]+\.js)"', ENTRY.read_text("utf-8"))
    assert imports, "the entry point imports nothing"
    missing = [name for name in imports if not (CLIENTS / name).is_file()]
    assert missing == []


def test_the_entry_point_exports_every_module_it_has():
    """A module nobody can import is a module that was written for nothing."""
    exported = set(re.findall(r'from "\./([a-z0-9_]+\.js)"', ENTRY.read_text("utf-8")))
    everything = {path.name for path in MODULES} - {"echoturn-client.js", "worklet.js"}
    assert everything - exported == set()
