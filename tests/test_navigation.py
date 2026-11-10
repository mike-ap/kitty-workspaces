from types import SimpleNamespace

from kitty_workspaces import navigation
from kitty_workspaces.workspace import Session


def test_next_agent_cycles_only_native_blocked_and_error(monkeypatch):
    tabs = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    windows = [
        [SimpleNamespace(id=n) for n in (1, 2, 3)],
        [SimpleNamespace(id=n) for n in (4, 5, 6)],
    ]

    class Tab(list):
        pass

    tabs = [Tab(panes) for panes in windows]
    for identity, tab in enumerate(tabs, 1):
        tab.id = identity
    values = {
        1: [
            Session("claude", i, i * 10, "Task", s)
            for i, s in [(1, "idle"), (2, "working"), (3, "done")]
        ],
        2: [
            Session("codex", i, i * 10, "Task", s)
            for i, s in [(4, "blocked"), (5, "error"), (6, None)]
        ],
    }
    monkeypatch.setattr(navigation, "sessions", lambda tab: values[tab.id])
    boss = SimpleNamespace(all_tabs=tabs, active_window=windows[0][0])

    def focus(identity, switch_os_window_if_needed):
        assert switch_os_window_if_needed
        boss.active_window = SimpleNamespace(id=identity)

    boss.set_active_window = focus
    for expected in (4, 5, 4):
        assert navigation.next_agent(boss) == {"window_id": expected, "tab_id": 2}
    values[2] = []
    assert navigation.next_agent(boss) is None
