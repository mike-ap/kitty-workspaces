"""Process polling worker with independent background Git observation."""

import argparse
import contextlib
import fcntl
import json
import os
import shutil
import signal
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import monotonic, sleep, time

from . import agents, worktrees
from .git_cache import GitCache


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w", dir=path.parent, delete=False, encoding="utf-8"
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def observe_processes(entry, groups):
    """Read process metadata only in the worker, sharing one scan per poll."""
    from kitty.child import cmdline_of_pid, cwd_of_process

    processes = []
    for pid in sorted(groups.get(entry.get("foreground_pgrp"), [])):
        try:
            processes.append(
                {"pid": pid, "cmdline": cmdline_of_pid(pid), "cwd": cwd_of_process(pid)}
            )
        except (OSError, ValueError):
            continue
    return processes


def collect_panes(input_path):
    from kitty.child import environ_of_process

    try:
        inputs = json.loads(input_path.read_text())
    except (OSError, ValueError):
        return []
    groups = None
    panes = []
    for entry in inputs:
        processes = []
        reported_processes = entry.get("processes")
        if reported_processes is None:
            if groups is None:
                from kitty.child import process_group_map

                groups = process_group_map()
            reported_processes = observe_processes(entry, groups)
        cwd = None
        for reported in sorted(reported_processes, key=lambda p: p["pid"]):
            try:
                adapter = agents.for_command(reported.get("cmdline") or [])
                if (
                    adapter is not None
                    and adapter.exclude_environment is not None
                    and adapter.exclude_environment(environ_of_process(reported["pid"]))
                ):
                    continue
                cwd = cwd or reported.get("cwd")
                if adapter is not None:
                    # Never persist arguments, environments, or unrelated processes.
                    processes.append(
                        {
                            "pid": reported["pid"],
                            "agent": adapter.id,
                            "cwd": reported.get("cwd"),
                        }
                    )
            except (OSError, ValueError):
                continue
        if not cwd and "processes" not in entry:
            from kitty.child import cwd_of_process

            with contextlib.suppress(OSError, ValueError):
                cwd = cwd_of_process(entry["root_pid"])
        cwd = cwd or entry.get("cwd")
        panes.append(
            {
                "id": entry["id"],
                "root_pid": entry.get("root_pid"),
                "foreground_pgrp": entry.get("foreground_pgrp"),
                "processes": processes,
                "cwd": cwd,
                "label": worktrees.fallback_label(cwd)
                if cwd
                else entry.get("title", ""),
                "repository_root": None,
                "worktree_root": None,
                "branch": None,
            }
        )
    return panes


def parent_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def run(output, input_path, parent, interval=2, once=False):
    stopped = False

    def stop(*args):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # Kitty may block these signals for its own event loop; do not inherit that
    # policy in the standalone worker. Install handlers before unblocking.
    signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGTERM, signal.SIGINT})
    with output.with_suffix(".lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        git_cache = GitCache()
        try:
            poll(output, input_path, parent, interval, once, lambda: stopped, git_cache)
        finally:
            git_cache.close()


def poll(output, input_path, parent, interval, once, stopped, git_cache):
    while not stopped() and parent_alive(parent):
        started = monotonic()
        try:
            panes = collect_panes(input_path)
            git_cache.enrich(panes)
            write_json(output, {"observed_at": time(), "error": None, "panes": panes})
        except Exception as error:
            write_json(
                output,
                {
                    "observed_at": time(),
                    "error": f"{type(error).__name__}: {error}",
                    "panes": [],
                },
            )
        if once:
            break
        deadline = started + interval
        while not stopped():
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            sleep(min(0.2, remaining))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--parent", type=int, required=True)
    parser.add_argument("--interval", type=float, default=2)
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove the private output directory after exit",
    )
    args = parser.parse_args()
    if args.interval <= 0 or args.parent <= 1:
        parser.error("interval must be positive and parent must be a process ID > 1")
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    run(args.output, args.input, args.parent, args.interval, args.once)
    if args.cleanup:
        # Used only for runtime-owned private directories. Parent death also
        # handles Kitty exiting before its daemon cleanup thread can finish.
        shutil.rmtree(args.output.parent, ignore_errors=True)
