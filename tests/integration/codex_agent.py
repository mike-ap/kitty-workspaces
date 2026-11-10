"""A foreground process named codex emitting OSC 7501 without a busy footer."""

import os
import sys

if len(sys.argv) < 2 or sys.argv[1] != "--running":
    for key in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_TOOL_CALL_ID"):
        os.environ.pop(key, None)
    os.execv(sys.executable, ["codex", __file__, "--running", *sys.argv[1:]])


def draw(state):
    print(
        f"\x1b]0;Duplicate | project\x07\x1b]7501;state={state}:app=codex\x1b\\READY Duplicate",
        flush=True,
    )


draw(sys.argv[2])
for line in sys.stdin:
    if line.strip() in {"idle", "working", "done", "blocked", "error", "clear"}:
        draw(line.strip())
