"""Configure with: watcher kitty_workspaces/watcher.py"""

import sys
from pathlib import Path


def on_focus_change(boss, window, data):
    if not data.get("focused"):
        return
    directory = str(Path(__file__).resolve().parents[1])
    if directory not in sys.path:
        sys.path.insert(0, directory)
    from kitty_workspaces import runtime

    state = runtime.start(boss)
    tab = window.tabref()
    if state is not None and tab is not None:
        state.recency.visit(tab.id)
