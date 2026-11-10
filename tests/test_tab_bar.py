from types import SimpleNamespace

import pytest

from kitty_workspaces import tab_bar
from kitty_workspaces.workspace import Session, Workspace


def test_vertical_titles_keep_two_rows_across_activity_and_fallbacks(monkeypatch):
    monkeypatch.setattr(tab_bar, "LEFT_EDGE", "left")
    monkeypatch.setattr(tab_bar, "RIGHT_EDGE", "right")
    tab = SimpleNamespace(name="")
    state = SimpleNamespace(workspaces={})
    monkeypatch.setattr(tab_bar.runtime, "current", lambda: state)
    monkeypatch.setattr(
        tab_bar, "get_boss", lambda: SimpleNamespace(tab_for_id=lambda tab_id: tab)
    )
    monkeypatch.setattr(
        tab_bar,
        "get_options",
        lambda: SimpleNamespace(tab_bar_edge="left", tab_title_max_lines=2),
    )
    data = {"tab_id": 1, "title": "Shell", "max_title_length": 40}
    for status in ("working", "idle"):
        session = Session("codex", 1, 10, "Task", status)
        state.workspaces[1] = Workspace(
            project="demo", sessions=[session], representative_session=session
        )
        assert len(tab_bar.draw_title(data).split("\n")) == 2
    state.workspaces[1] = Workspace(project="demo")
    assert tab_bar.draw_title(data) == " demo \n  "
    state.workspaces[1] = Workspace(manual_name="My workspace")
    assert tab_bar.draw_title(data) == "  \n My workspace "
    state.workspaces.clear()
    assert tab_bar.draw_title(data) == " Shell \n  "


@pytest.mark.parametrize(
    ("edge", "line_limit", "expected"),
    [
        ("top", 2, " demo · ● Session "),
        ("bottom", 2, " demo · ● Session "),
        ("left", 2, " demo \n ● Session "),
        ("right", 2, " demo \n ● Session "),
        ("left", 1, " demo · ● Session "),
        ("right", 1, " demo · ● Session "),
    ],
)
def test_draw_title_adapts_to_current_kitty_options(
    monkeypatch, edge, line_limit, expected
):
    monkeypatch.setattr(tab_bar, "LEFT_EDGE", "left")
    monkeypatch.setattr(tab_bar, "RIGHT_EDGE", "right")
    monkeypatch.setattr(
        tab_bar, "get_boss", lambda: SimpleNamespace(tab_for_id=lambda tab_id: None)
    )
    options = SimpleNamespace(tab_bar_edge=edge, tab_title_max_lines=line_limit)
    monkeypatch.setattr(tab_bar, "get_options", lambda: options)
    data = {"tab_id": 1, "title": "demo\n● Session", "max_title_length": 40}

    assert tab_bar.draw_title(data) == expected

    # Read the options on each draw, including after a Kitty config reload.
    options.tab_bar_edge = "bottom"
    assert tab_bar.draw_title(data) == " demo · ● Session "


def test_draw_title_preserves_manual_name(monkeypatch):
    tab = type(
        "Tab",
        (),
        {
            "name": "My chosen name",
            "active_window": None,
            "__iter__": lambda self: iter([]),
        },
    )()
    monkeypatch.setattr(
        tab_bar, "get_boss", lambda: SimpleNamespace(tab_for_id=lambda tab_id: tab)
    )
    monkeypatch.setattr(
        tab_bar,
        "get_options",
        lambda: SimpleNamespace(tab_bar_edge="bottom", tab_title_max_lines=2),
    )

    assert (
        tab_bar.draw_title({"tab_id": 1, "title": "demo\nSession"})
        == " My chosen name "
    )
