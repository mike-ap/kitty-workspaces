import runpy
from pathlib import Path
from types import SimpleNamespace

from kitty_workspaces import navigation, runtime
from kitty_workspaces.recency import Recency


def test_visits_ignore_pane_changes_and_loss_of_focus_and_prune_closed_tabs():
    history = Recency()
    for identity in (1, 1, None, 2, 3, 1):
        history.visit(identity)
    assert history.visits == {1: 4, 2: 2, 3: 3}
    history.prune({1, 2})
    assert history.visits == {1: 4, 2: 2}
    assert history.current == 1
    history.prune({2})
    assert history.current is None


def test_previous_workspace_toggles_immediately_and_keeps_selected_pane(monkeypatch):
    class Tab(list):
        def __init__(self, identity, pane_id):
            self.id = identity
            self.active_window = SimpleNamespace(id=pane_id)
            super().__init__([self.active_window])

    tabs = [Tab(1, 10), Tab(2, 21), Tab(3, 30)]
    focused = [30]
    boss = SimpleNamespace(all_tabs=tabs)
    state = runtime.State(boss, Path("/unused"), Path("/unused/worker.py"))
    monkeypatch.setattr(state, "focused_pane", lambda: focused[0])
    monkeypatch.setattr(runtime, "_state", state)
    for identity in (1, 2, 3):
        state.recency.visit(identity)

    def focus(identity, switch_os_window_if_needed):
        assert switch_os_window_if_needed
        focused[0] = identity

    boss.set_active_window = focus
    for tab_id, pane_id in ((2, 21), (3, 30), (2, 21)):
        assert navigation.previous_workspace(boss) == {
            "tab_id": tab_id,
            "window_id": pane_id,
        }
    tabs.remove(tabs[2])
    assert navigation.previous_workspace(boss)["tab_id"] == 1
    tabs[:] = tabs[:1]
    assert navigation.previous_workspace(boss) is None


def test_watcher_records_event_tab_without_polling(monkeypatch):
    history = Recency()
    monkeypatch.setattr(runtime, "start", lambda boss: SimpleNamespace(recency=history))
    watcher = runpy.run_path(
        str(Path(__file__).parents[1] / "src/kitty_workspaces/watcher.py")
    )
    window = SimpleNamespace(tabref=lambda: SimpleNamespace(id=42))
    watcher["on_focus_change"](None, window, {"focused": False})
    assert not history.visits
    watcher["on_focus_change"](None, window, {"focused": True})
    assert history.visits == {42: 1}
