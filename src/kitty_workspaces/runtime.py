"""Maintain a memory snapshot on Kitty's timer, outside tab-bar drawing."""

import atexit
import json
import os
import shutil
import subprocess
from concurrent.futures import Future
from pathlib import Path
from queue import Queue
from tempfile import mkdtemp
from threading import Thread
from time import monotonic, sleep, time

from .recency import Recency

_state = None


def boss_instance():
    try:
        from kitty.fast_data_types import get_boss

        return get_boss()
    except ImportError:
        return None


def current():
    return _state


def health():
    state = current()
    observed = state.observed_at if state else None
    return {
        "observed_at": observed,
        "error": state.error if state else None,
        "stale": observed is None or not 0 <= time() - observed <= 10,
    }


def collector_command(script):
    from kitty.constants import kitty_exe

    bootstrap = (
        "import runpy, sys; from pathlib import Path; "
        "script = sys.argv[1]; sys.path.insert(0, str(Path(script).parents[1])); "
        "sys.argv = sys.argv[1:]; runpy.run_path(script, run_name='__main__')"
    )
    return [kitty_exe(), "+runpy", bootstrap, str(script)]


def pane_observation(window):
    state = current()
    if state is None or health()["stale"] or state.error:
        return {}
    pane = getattr(state, "panes", {}).get(window.id, {})
    # Never attach an observation to a different root process reusing an ID.
    if pane.get("root_pid") != window.child.root_pid:
        return {}
    try:
        group = (
            os.tcgetpgrp(window.child.child_fd)
            if window.child.child_fd is not None
            else None
        )
    except OSError:
        group = None
    return pane if pane.get("foreground_pgrp") == group else {**pane, "processes": []}


def exchange_snapshots(directory, requests):
    """Exchange plain data on a daemon thread; never access Kitty objects here."""
    from .collector import write_json

    while (request := requests.get()) is not None:
        panes, result = request
        try:
            write_json(directory / "panes.json", panes)
            try:
                value = json.loads((directory / "snapshot.json").read_text())
            except (OSError, ValueError):
                value = None
            result.set_result(value)
        except Exception as error:
            result.set_exception(error)


class State:
    def __init__(self, boss, directory, script):
        self.boss = boss
        self.directory = directory
        self.script = script
        self.observed_at = None
        self.error = None
        self.panes = {}
        self.workspaces = {}
        self.recency = Recency()
        self.process = None
        self.last_start = -100
        self.timer = None
        self.closed = False
        self.io_requests = Queue()
        self.io_result = None
        self.io_thread = None

    def focused_pane(self):
        from kitty.fast_data_types import current_focused_os_window_id

        focused_os_window = current_focused_os_window_id()
        for tab in self.boss.all_tabs:
            manager = tab.tab_manager_ref()
            if (
                tab.os_window_id == focused_os_window
                and manager is not None
                and manager.active_tab is tab
                and tab.active_window is not None
            ):
                return tab.active_window.id
        return None

    def update_recency(self):
        tabs = list(self.boss.all_tabs)
        self.recency.prune({tab.id for tab in tabs})
        pane_id = self.focused_pane()
        for tab in tabs:
            if any(pane.id == pane_id for pane in tab):
                self.recency.visit(tab.id)
                break

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.io_requests.put(None)
        # Finish outstanding writes before stopping the worker and removing files.
        # Never wait for storage or process exit on Kitty's UI thread.
        self.cleanup_thread = Thread(target=self.cleanup, daemon=True)
        self.cleanup_thread.start()

    def cleanup(self):
        if self.io_thread is not None:
            self.io_thread.join()
        if self.process is not None:
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            except ProcessLookupError:
                pass
        shutil.rmtree(self.directory, ignore_errors=True)

    def launch(self):
        if self.process is not None and self.process.poll() is None:
            return
        if monotonic() - self.last_start < 10:
            return
        self.last_start = monotonic()
        try:
            with (self.directory / "collector.log").open("ab") as log:
                self.process = subprocess.Popen(
                    [
                        *collector_command(self.script),
                        "--output",
                        str(self.directory / "snapshot.json"),
                        "--input",
                        str(self.directory / "panes.json"),
                        "--cleanup",
                        "--parent",
                        str(os.getpid()),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
        except OSError as error:
            self.error = str(error)

    def refresh(self, timer_id=None):
        if self.closed:
            return
        from .workspace import resolve

        self.update_recency()
        self.launch()
        panes = []
        for tab in self.boss.all_tabs:
            for pane in tab:
                try:
                    group = (
                        os.tcgetpgrp(pane.child.child_fd)
                        if pane.child.child_fd is not None
                        else None
                    )
                except OSError:
                    group = None
                panes.append(
                    {
                        "id": pane.id,
                        "root_pid": pane.child.root_pid,
                        "foreground_pgrp": group,
                        "title": pane.title,
                        # Process discovery and cwd reads belong to the worker.
                        "cwd": pane.child.cwd,
                    }
                )
        # Kitty holds the GIL while its native event loop is idle. Yield it
        # explicitly so the exchange thread can run even without UI activity.
        # Allow a small scheduling window; never wait for storage or a result.
        sleep(0.001)
        # Never wait for storage on Kitty's event loop. Keep at most one exchange
        # outstanding, even if a slow filesystem takes longer than the timer.
        if self.io_result is not None and self.io_result.done():
            try:
                value = self.io_result.result()
                if isinstance(value, dict) and isinstance(value.get("panes"), list):
                    self.observed_at = value.get("observed_at")
                    self.error = value.get("error")
                    self.panes = {pane["id"]: pane for pane in value["panes"]}
            except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
                self.error = str(error)
            self.io_result = None
        if self.io_result is None:
            if self.io_thread is None:
                self.io_thread = Thread(
                    target=exchange_snapshots,
                    args=(self.directory, self.io_requests),
                    daemon=True,
                    name="kitty-workspaces-io",
                )
                self.io_thread.start()
            self.io_result = Future()
            self.io_requests.put((panes, self.io_result))
        workspaces = {
            tab.id: resolve(tab, tab.title, tab.id) for tab in self.boss.all_tabs
        }
        if workspaces != self.workspaces:
            self.workspaces = workspaces
            for manager in self.boss.os_window_map.values():
                # Dirtying only schedules a repaint of the existing screen.
                # Rebuild it so custom titles see the new workspace snapshot.
                manager.update_tab_bar_data()
                manager.mark_tab_bar_dirty()


def start(boss=None):
    global _state
    if _state is not None:
        return _state
    boss = boss if boss is not None else boss_instance()
    if boss is None:
        return None
    from kitty.fast_data_types import add_timer

    root = (
        Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        / "kitty-workspaces"
    )
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = Path(mkdtemp(prefix=f"{os.getpid()}-", dir=root))
    script = Path(__file__).resolve().parent / "worker.py"
    state = State(boss, directory, script)
    _state = state
    atexit.register(state.close)
    # Schedule startup as well as refresh outside draw_title().
    state.timer = add_timer(state.refresh, 0.5, True)
    return state
