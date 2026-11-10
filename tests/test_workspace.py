from types import SimpleNamespace

import pytest

from kitty_workspaces import workspace
from kitty_workspaces.labels import workspace_lines


class Tab(list):
    name = ""

    def __init__(self, windows):
        super().__init__(windows)
        self.active_window = windows[-1] if windows else None


@pytest.fixture(autouse=True)
def cached_panes(monkeypatch):
    monkeypatch.setattr(workspace.runtime, "pane_observation", lambda w: w.observation)


def pane(identity, agent="claude", status="idle", title="✳ Task"):
    return SimpleNamespace(
        id=identity,
        title=title,
        observation={
            "cwd": "/demo",
            "label": "demo\nbranch",
            "processes": [{"pid": identity * 10, "agent": agent, "cwd": "/demo"}],
        },
        program_status=SimpleNamespace(
            as_list=lambda: [
                {"app": "claude-code" if agent == "claude" else agent, "state": status}
            ]
        ),
    )


def test_workspace_identity_focus_and_manual_name_preserve_native_status():
    tab = Tab([pane(1), pane(2, "codex", "blocked", "Question | demo")])
    item = workspace.resolve(tab, "Fallback", 42)
    assert item.id == 42 and item.cwd == "/demo"
    assert item.representative_session.agent == "claude"
    assert [s.window_id for s in item.sessions] == [1, 2]
    assert item.status == "blocked"
    assert workspace_lines(item) == "demo\n? Task"
    tab.name = "Manual"
    assert workspace_lines(workspace.resolve(tab, "Fallback")) == "demo\n? Manual"
    assert item.session_counts == {
        "total": 2,
        "idle": 1,
        "working": 0,
        "done": 0,
        "blocked": 1,
        "error": 0,
        "unknown": 0,
    }


def test_duplicate_app_processes_are_unknown_until_one_exits():
    window = pane(1, "codex", "working")
    window.observation["processes"].append({"pid": 99, "agent": "codex"})
    assert [s.status for s in workspace.sessions(Tab([window]))] == [None, None]
    window.observation["processes"].pop()
    assert [s.status for s in workspace.sessions(Tab([window]))] == ["working"]


def test_reports_are_read_live_and_missing_reports_do_not_infer_idle():
    window = pane(1)
    tab = Tab([window])
    assert workspace.sessions(tab)[0].status == "idle"
    window.program_status.as_list = list
    assert workspace.sessions(tab)[0].status is None


@pytest.mark.parametrize(
    "title, expected",
    [
        ("✳ Fix CI", "Fix CI"),
        ("◑ Review", "Review"),
        ("✳ Claude Code", None),
        ("demo-90", None),
    ],
)
def test_claude_terminal_titles(title, expected):
    assert workspace.sessions(Tab([pane(1, title=title)]))[0].title == expected


def test_title_owner_survives_focus_and_layout_changes_then_hands_over():
    oldest = pane(1, title="✳ First")
    newer = pane(2, "codex", "blocked", "Second | demo")
    tab = Tab([newer, oldest])
    for focused in (oldest, newer):
        tab.active_window = focused
        item = workspace.resolve(tab, "Fallback")
        assert item.representative_session.window_id == oldest.id
        assert workspace_lines(item) == "demo\n? First"
    oldest.observation["processes"] = []
    item = workspace.resolve(tab, "Fallback")
    assert item.representative_session.window_id == newer.id
    assert workspace_lines(item) == "demo\n? Second"


def test_titleless_owner_uses_worktree_instead_of_newer_agent_title():
    tab = Tab([pane(1, title="Claude Code"), pane(2, title="✳ Newer")])
    item = workspace.resolve(tab, "Fallback")
    assert item.representative_session.window_id == 1
    assert workspace_lines(item) == "demo\n○ branch"
