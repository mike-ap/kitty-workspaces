"""Clean Claude's terminal title for display."""

import re
from pathlib import Path


def terminal_title(title, cwd=None):
    """Use Claude's descriptive OSC title, without its activity decoration."""
    title = re.sub(r"^[✳✻✽✶✢◐◓◑◒]\ufe0f?\s*", "", (title or "").strip()).strip()
    if not title or title.casefold() in {"claude", "claude code"}:
        return None
    if cwd and re.fullmatch(re.escape(Path(cwd).name) + r"-[0-9a-fA-F]{2}", title):
        return None
    return title
