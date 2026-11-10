import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from kitty_workspaces import commands, metadata, navigation, runtime


@pytest.fixture
def boss(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "kitty.fast_data_types",
        SimpleNamespace(current_focused_os_window_id=lambda: 7),
    )
    monkeypatch.setattr(runtime, "start", lambda boss: None)
    return SimpleNamespace(all_tabs=[])


@pytest.mark.parametrize(
    "command", ["state", "health", "next-agent", "previous-workspace"]
)
def test_dispatch(command, boss, monkeypatch):
    monkeypatch.setattr(
        metadata, "snapshot", lambda tabs, focused: {"focused": focused}
    )
    monkeypatch.setattr(runtime, "health", lambda: {"stale": True})
    monkeypatch.setattr(navigation, "next_agent", lambda boss: {"window_id": 2})
    monkeypatch.setattr(navigation, "previous_workspace", lambda boss: None)
    expected = {
        "state": {"focused": 7},
        "health": {"stale": True},
        "next-agent": {"window_id": 2},
        "previous-workspace": None,
    }
    assert (
        json.loads(commands.execute(["kitten.py", command], boss)) == expected[command]
    )


@pytest.mark.parametrize(
    "args", [["kitten.py", "bad"], ["kitten.py", "state", "extra"]]
)
def test_invalid_command(args, boss):
    with pytest.raises(ValueError, match="Usage:"):
        commands.execute(args, boss)


def test_endpoint_defaults_to_state(boss, monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "kittens.tui.handler",
        SimpleNamespace(result_handler=lambda **kwargs: lambda f: f),
    )
    monkeypatch.setattr(metadata, "snapshot", lambda *args: {"version": 1})
    endpoint = Path(runtime.__file__).with_name("kitten.py")
    kitten = runpy.run_path(str(endpoint))
    assert kitten["main"]([]) is None
    assert json.loads(kitten["handle_result"]([str(endpoint)], None, 0, boss)) == {
        "version": 1
    }
