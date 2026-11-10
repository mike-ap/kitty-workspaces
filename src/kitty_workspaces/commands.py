"""Shared no-UI kitten commands."""

import json


def execute(args, boss):
    from kitty.fast_data_types import current_focused_os_window_id

    from . import runtime
    from .metadata import snapshot

    command = args[1] if len(args) > 1 else "state"
    if (
        command not in ("state", "health", "next-agent", "previous-workspace")
        or len(args) > 2
    ):
        raise ValueError(
            "Usage: kitty_workspaces/kitten.py [state|health|next-agent|previous-workspace]"
        )
    runtime.start(boss)
    if command == "previous-workspace":
        from .navigation import previous_workspace

        return json.dumps(previous_workspace(boss))
    if command == "next-agent":
        from .navigation import next_agent

        return json.dumps(next_agent(boss))
    if command == "health":
        return json.dumps(runtime.health())
    return json.dumps(snapshot(boss.all_tabs, current_focused_os_window_id()))
