"""Copy into Kitty's config directory to enable workspace tab names."""

import sys
from pathlib import Path

# Kitty does not necessarily include its configuration directory on sys.path.
directory = str(Path(__file__).parent)
if directory not in sys.path:
    sys.path.insert(0, directory)

import kitty_workspaces  # noqa: E402 — configuration path must be added first

kitty_workspaces.runtime.start()


def draw_title(data):
    return kitty_workspaces.tab_bar.draw_title(data)
