"""Kitty Workspaces commands, run with kitten @ kitten kitty_workspaces/kitten.py."""

import sys
from pathlib import Path

from kittens.tui.handler import result_handler


def main(args):
    pass


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss):
    # Custom kittens have no __file__. Load the same package as the tab-bar hook.
    directory = str(Path(args[0]).resolve().parents[1])
    if directory not in sys.path:
        sys.path.insert(0, directory)
    from kitty_workspaces.commands import execute

    return execute(args, boss)
