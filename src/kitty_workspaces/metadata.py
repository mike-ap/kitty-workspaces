"""Versioned public workspace metadata for independent consumers."""

from dataclasses import asdict

from . import runtime
from .labels import workspace_lines
from .status import STATUS_MARKERS
from .workspace import resolve

VERSION = 1


def session_data(session):
    return {**asdict(session), "status_character": STATUS_MARKERS[session.status]}


def snapshot(tabs, focused_os_window_id=None):
    state = runtime.current()
    if state is not None:
        state.update_recency()
    visits = state.recency.visits if state is not None else {}
    workspaces = []
    for tab in tabs:
        item = resolve(tab, tab.title, tab.id)
        manager = tab.tab_manager_ref()
        is_active = manager is not None and manager.active_tab is tab
        workspaces.append(
            {
                **asdict(item),
                "sessions": [session_data(session) for session in item.sessions],
                "representative_session": (
                    session_data(item.representative_session)
                    if item.representative_session
                    else None
                ),
                "status": item.status,
                "status_character": STATUS_MARKERS[item.status],
                "session_counts": item.session_counts,
                "name": workspace_lines(item),
                "window_ids": [window.id for window in tab],
                "active_window_id": tab.active_window.id if tab.active_window else None,
                "os_window_id": tab.os_window_id,
                "last_visited_order": visits.get(tab.id),
                "is_active": is_active,
                "is_focused": is_active and tab.os_window_id == focused_os_window_id,
            }
        )
    return {"version": VERSION, "collector": runtime.health(), "workspaces": workspaces}
