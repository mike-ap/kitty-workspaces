from types import SimpleNamespace

from kitty_workspaces import metadata, runtime
from kitty_workspaces.workspace import Session, Workspace


def test_version_one_publishes_native_state_and_process_identity(monkeypatch):
    class Tab(list):
        id = 42
        title = "Task"
        os_window_id = 7

        def tab_manager_ref(self):
            return SimpleNamespace(active_tab=self)

    tab = Tab([SimpleNamespace(id=8)])
    tab.active_window = tab[0]
    session = Session("codex", 8, 123, "Task", "done", "/demo")
    monkeypatch.setattr(
        metadata,
        "resolve",
        lambda *args: Workspace(
            id=42, project="demo", sessions=[session], representative_session=session
        ),
    )
    monkeypatch.setattr(runtime, "_state", None)
    result = metadata.snapshot([tab], 7)
    assert result["version"] == 1
    assert set(result) == {"version", "collector", "workspaces"}
    item = result["workspaces"][0]
    assert item["status"] == "done" and item["status_character"] == "✓"
    assert item["is_active"] and item["is_focused"]
    assert item["sessions"] == [
        {
            "agent": "codex",
            "window_id": 8,
            "pid": 123,
            "title": "Task",
            "status": "done",
            "cwd": "/demo",
            "status_character": "✓",
        }
    ]
