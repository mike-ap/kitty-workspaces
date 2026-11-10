"""New adapters work through collection and session assembly without core edits."""

import json
import sys
from types import SimpleNamespace

import pytest

from kitty_workspaces import agents, collector, workspace
from kitty_workspaces.status import reported_status


@pytest.mark.parametrize("status_app", ["example-cli", None])
def test_registered_adapter_flows_through_collector_and_workspace(
    monkeypatch, tmp_path, status_app
):
    adapter = agents.AgentAdapter(
        "example",
        ("example", "example-preview"),
        status_app,
        normalize_title=lambda title, cwd: title.removeprefix("Example: "),
        exclude_environment=lambda env: "EXAMPLE_TOOL" in env,
    )
    monkeypatch.setattr(agents, "ADAPTERS", (*agents.ADAPTERS, adapter))
    inspected = []

    def environment(pid):
        inspected.append(pid)
        return {"EXAMPLE_TOOL": "secret"} if pid == 2 else {}

    monkeypatch.setitem(
        sys.modules, "kitty.child", SimpleNamespace(environ_of_process=environment)
    )
    inputs = tmp_path / "panes.json"
    inputs.write_text(
        json.dumps(
            [
                {
                    "id": 1,
                    "processes": [
                        {"pid": 1, "cmdline": ["/bin/example-preview"], "cwd": "/demo"},
                        {"pid": 2, "cmdline": ["example"]},
                        {"pid": 3, "cmdline": ["sh"]},
                        {"pid": 4, "cmdline": ["claude"]},
                    ],
                }
            ]
        )
    )
    (observation,) = collector.collect_panes(inputs)
    assert inspected == [1, 2]
    assert "EXAMPLE_TOOL" not in json.dumps(observation)
    assert "secret" not in json.dumps(observation)
    monkeypatch.setattr(workspace.runtime, "pane_observation", lambda w: observation)
    window = SimpleNamespace(
        id=1,
        title="Example: Task",
        program_status=SimpleNamespace(
            as_list=lambda: [{"app": "example-cli", "state": "blocked"}]
        ),
    )
    session, claude = workspace.sessions([window])
    assert session.agent == "example"
    assert session.pid == 1
    assert session.title == "Task"
    assert session.cwd == "/demo"
    assert session.status == ("blocked" if status_app else None)
    assert claude.agent == "claude"
    assert claude.status is None


@pytest.mark.parametrize("command", [[], ["sh"], ["claude-helper"], ["codex-helper"]])
def test_unrecognized_commands_are_not_agents(command):
    assert agents.for_command(command) is None


def test_custom_command_matching_and_registration_order(monkeypatch):
    adapter = agents.AgentAdapter(
        "wrapped",
        (),
        matches_command=lambda cmd: len(cmd) > 1 and cmd[:2] == ["node", "agent.js"],
    )
    monkeypatch.setattr(agents, "ADAPTERS", (adapter, *agents.ADAPTERS))
    assert agents.for_command(["node", "agent.js", "--interactive"]) is adapter
    assert agents.for_command(["node", "other.js"]) is None
    assert agents.for_command([]) is None
    assert adapter.normalize_title(" Task ", None) == "Task"
    assert adapter.normalize_title(" ", None) is None


def test_unregistered_agent_status_is_unknown():
    assert reported_status(SimpleNamespace(), "unregistered") is None
