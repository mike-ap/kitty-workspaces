"""A foreground process named claude emitting native OSC 7501 reports."""

import os
import sys


def main():
    args = sys.argv[1:]
    if args[0] != "--running":
        os.execv(sys.executable, ["claude", __file__, "--running", *args])
    title, state = args[1:3]

    def report(state):
        print(
            f"\x1b]0;✳ {title}\x07\x1b]7501;state={state}:app=claude-code\x1b\\READY {title}",
            flush=True,
        )

    report(state)
    for line in sys.stdin:
        if line.strip() in {"idle", "working", "done", "blocked", "error", "clear"}:
            report(line.strip())


if __name__ == "__main__":
    main()
