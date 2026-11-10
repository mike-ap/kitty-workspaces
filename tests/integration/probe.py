"""Read Kitty's rendered tab-bar screen through a test-only no-UI kitten."""

import json

from kittens.tui.handler import result_handler


def main(args):
    pass


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss):
    window = boss.window_id_map[target_window_id]
    manager = boss.os_window_map[window.os_window_id]
    bar = manager.tab_bar
    rows = [str(bar.screen.line(row)) for row in range(bar.screen.lines)]
    labels = {
        str(extent.tab_id): [
            rows[row][extent.x.start : extent.x.end + 1].strip()
            for row in range(extent.y.start, extent.y.end + 1)
        ]
        for extent in bar.tab_extents
    }
    return json.dumps(
        {
            "rows": rows,
            "labels": labels,
            "active_tab": manager.active_tab.id,
            "active_window": manager.active_tab.active_window.id,
            "processes": [
                {"id": pane.id, "foreground": pane.child.foreground_processes}
                for pane in manager.active_tab
            ],
        }
    )
