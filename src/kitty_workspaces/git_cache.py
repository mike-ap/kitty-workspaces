"""Refresh Git independently so slow storage cannot stall agent discovery."""

from threading import Event, Lock, Thread
from time import monotonic

from . import worktrees

REFRESH_SECONDS = 10
EXPIRY_SECONDS = 30


class GitCache:
    def __init__(self):
        self.lock = Lock()
        self.wake = Event()
        self.stopped = False
        self.directories = ()
        self.results = {}
        self.thread = Thread(target=self.run, daemon=True, name="kitty-workspaces-git")
        self.thread.start()

    def close(self):
        # A filesystem call may be blocked. Do not wait for it on shutdown.
        with self.lock:
            self.stopped = True
        self.wake.set()

    def enrich(self, panes):
        """Use completed, fresh observations; replace pending work, never queue it."""
        directories = tuple(
            dict.fromkeys(pane["cwd"] for pane in panes if pane.get("cwd"))
        )
        now = monotonic()
        with self.lock:
            self.directories = directories
            self.results = {
                cwd: value for cwd, value in self.results.items() if cwd in directories
            }
            for pane in panes:
                observed, fields = self.results.get(
                    pane.get("cwd"), (-float("inf"), {})
                )
                if now - observed <= EXPIRY_SECONDS:
                    pane.update(fields)
        self.wake.set()

    def run(self):
        while True:
            self.wake.wait()
            self.wake.clear()
            with self.lock:
                if self.stopped:
                    return
                directories = self.directories
            refresh = int(monotonic() // REFRESH_SECONDS)
            for cwd in directories:
                with self.lock:
                    if self.stopped:
                        return
                    if cwd not in self.directories:
                        continue
                    observed = self.results.get(cwd, (-float("inf"), {}))[0]
                if monotonic() - observed < REFRESH_SECONDS:
                    continue
                # Never hold the lock during Git, configuration, or filesystem I/O.
                started = monotonic()
                try:
                    label = worktrees.label(cwd, refresh)
                    repository, root, branch = worktrees.context(cwd, refresh)
                    fields = {
                        "label": label,
                        "repository_root": repository,
                        "worktree_root": root,
                        "branch": branch,
                    }
                except Exception:
                    # Keep process collection alive even if Git observation fails.
                    fields = {}
                with self.lock:
                    if cwd in self.directories and not self.stopped:
                        self.results[cwd] = (started, fields)
