from types import SimpleNamespace

import pytest

from kitty_workspaces.status import STATES, aggregate, reported_status


@pytest.mark.parametrize("agent, app", [("claude", "claude-code"), ("codex", "codex")])
@pytest.mark.parametrize("state", STATES)
def test_native_states_are_used_verbatim(agent, app, state):
    window = SimpleNamespace(
        program_status=SimpleNamespace(as_list=lambda: [{"app": app, "state": state}])
    )
    assert reported_status(window, agent) == state


@pytest.mark.parametrize(
    "records",
    [[], [{"app": "other", "state": "working"}], [{"app": "codex", "state": "future"}]],
)
def test_missing_unrelated_or_unknown_reports_are_unknown(records):
    window = SimpleNamespace(program_status=SimpleNamespace(as_list=lambda: records))
    assert reported_status(window, "codex") is None
    assert reported_status(SimpleNamespace(), "codex") is None


def test_report_urgency_includes_subtasks_and_excludes_other_apps():
    records = [{"app": "codex", "state": state} for state in STATES]
    window = SimpleNamespace(program_status=SimpleNamespace(as_list=lambda: records))
    assert reported_status(window, "codex") == "blocked"
    assert reported_status(window, "claude") is None


@pytest.mark.parametrize(
    "values, expected",
    [
        ([], None),
        (["idle"], "idle"),
        ([None, "idle"], None),
        (["working", None], "working"),
        (["working", "done"], "done"),
        (["done", "error"], "error"),
        (["error", "blocked"], "blocked"),
    ],
)
def test_aggregate_matches_native_urgency(values, expected):
    assert aggregate([SimpleNamespace(status=s) for s in values]) == expected
