"""Focus the next pane with an explicit, usable attention observation."""

from .workspace import sessions


def next_agent(boss):
    # Use live tab/pane order rather than title-owner order.
    # Rebuild sessions on invocation so source freshness and foreground-process
    # guards are checked even when the timer's cached workspace is older.
    panes = []
    pending = set()
    for tab in boss.all_tabs:
        panes.extend((window.id, tab.id) for window in tab)
        pending.update(
            session.window_id
            for session in sessions(tab)
            if session.status in {"blocked", "error"}
        )
    current = boss.active_window
    anchor = next(
        (
            index
            for index, (identity, _) in enumerate(panes)
            if current is not None and identity == current.id
        ),
        -1,
    )
    for identity, tab_id in panes[anchor + 1 :] + panes[: anchor + 1]:
        if identity in pending:
            boss.set_active_window(identity, switch_os_window_if_needed=True)
            return {"window_id": identity, "tab_id": tab_id}
    return None


def previous_workspace(boss):
    from . import runtime

    state = runtime.current()
    if state is None:
        return None
    state.update_recency()
    history = state.recency
    tabs = {tab.id: tab for tab in boss.all_tabs}
    for identity in sorted(history.visits, key=history.visits.get, reverse=True):
        if identity == history.current:
            continue
        tab = tabs[identity]
        pane = tab.active_window
        if pane is None:
            continue
        boss.set_active_window(pane.id, switch_os_window_if_needed=True)
        history.visit(identity)
        return {"window_id": pane.id, "tab_id": identity}
    return None
