"""Render workspace identity in Kitty's tab bar."""

try:
    from kitty.fast_data_types import LEFT_EDGE, RIGHT_EDGE, get_boss, get_options
except ImportError:
    get_boss = get_options = None
    LEFT_EDGE = RIGHT_EDGE = None

from . import runtime
from .labels import render_title, workspace_lines


def draw_title(data):
    tab = get_boss().tab_for_id(data["tab_id"])
    state = runtime.current()
    item = state.workspaces.get(data["tab_id"]) if state else None
    title = (
        workspace_lines(item)
        if item
        else tab.name
        if tab is not None and tab.name
        else data["title"]
    )
    width = max(1, data.get("max_title_length") or 20)
    options = get_options()
    multiline = (
        options.tab_bar_edge in (LEFT_EDGE, RIGHT_EDGE)
        and options.tab_title_max_lines >= 2
    )
    return render_title(title, width, multiline)
