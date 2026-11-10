import json
import sys
from types import SimpleNamespace

import pytest

from kitty_workspaces import collector, runtime, tab_bar, workspace


@pytest.mark.parametrize(
    "tool_env",
    [
        {"CODEX_THREAD_ID": "parent"},
        {"CODEX_SESSION_ID": "parent"},
        {"CODEX_TOOL_CALL_ID": "call"},
    ],
)
def test_codex_tool_processes_are_excluded_without_retaining_environment(
    monkeypatch, tmp_path, tool_env
):
    inputs = tmp_path / "panes.json"
    inputs.write_text(
        json.dumps(
            [
                {
                    "id": 1,
                    "root_pid": 10,
                    "foreground_pgrp": 20,
                    "processes": [
                        {
                            "pid": pid,
                            "cmdline": ["/bin/codex"] if pid in (20, 30) else ["sh"],
                            "cwd": "/work",
                        }
                        for pid in (20, 30, 40)
                    ],
                }
            ]
        )
    )
    inspected = []

    def environment(pid):
        inspected.append(pid)
        return {"KITTY_WINDOW_ID": "1", "SECRET": "not-for-snapshots"} | (
            tool_env if pid == 30 else {}
        )

    monkeypatch.setitem(
        sys.modules,
        "kitty.child",
        SimpleNamespace(
            cmdline_of_pid=lambda pid: ["/bin/codex"] if pid in (20, 30) else ["sh"],
            cwd_of_process=lambda pid: "/work",
            environ_of_process=environment,
            processes_in_group=lambda group: [20, 30, 40],
        ),
    )
    (pane,) = collector.collect_panes(inputs)
    assert pane["processes"] == [{"pid": 20, "agent": "codex", "cwd": "/work"}]
    assert inspected == [20, 30]
    assert "not-for-snapshots" not in json.dumps(pane)
    assert all(key not in json.dumps(pane) for key in tool_env)


def test_drawing_uses_memory_without_resolving_or_reading_files(monkeypatch):
    tab = SimpleNamespace(name="")
    state = SimpleNamespace(
        workspaces={1: workspace.Workspace(project="demo", worktree="branch")}
    )
    monkeypatch.setattr(
        tab_bar, "get_boss", lambda: SimpleNamespace(tab_for_id=lambda identity: tab)
    )
    monkeypatch.setattr(tab_bar.runtime, "current", lambda: state)
    monkeypatch.setattr(
        tab_bar,
        "get_options",
        lambda: SimpleNamespace(tab_bar_edge="bottom", tab_title_max_lines=1),
    )
    monkeypatch.setattr(
        workspace,
        "resolve",
        lambda *args: (_ for _ in ()).throw(AssertionError("resolve during draw")),
    )
    monkeypatch.setattr(
        runtime.Path,
        "read_text",
        lambda *args: (_ for _ in ()).throw(AssertionError("read during draw")),
    )
    assert (
        tab_bar.draw_title({"tab_id": 1, "title": "Fallback", "max_title_length": 40})
        == " demo · branch "
    )


def test_timer_avoids_process_discovery_and_uses_wrapper_aware_root(
    monkeypatch, tmp_path
):
    class Child:
        pid = 99
        root_pid = 42

        @property
        def current_cwd(self):
            raise AssertionError("cwd discovery in Kitty's timer")

        cwd = "/start"
        child_fd = None

        @property
        def foreground_processes(self):
            raise AssertionError("process discovery in Kitty's timer")

    class Window:
        id = 1
        title = "Task"
        child = Child()

        def get_cwd_of_child(self, **kwargs):
            raise AssertionError("cwd discovery in Kitty's timer")

    window = Window()
    tab = type(
        "Tab",
        (),
        {
            "id": 1,
            "name": "",
            "title": "Task",
            "active_window": window,
            "__iter__": lambda self: iter([window]),
        },
    )()
    redraws = []
    manager = SimpleNamespace(
        update_tab_bar_data=lambda: redraws.append("update"),
        mark_tab_bar_dirty=lambda: redraws.append("dirty"),
    )
    boss = SimpleNamespace(all_tabs=[tab], os_window_map={1: manager})
    state = runtime.State(boss, tmp_path, tmp_path / "worker.py")
    monkeypatch.setattr(state, "launch", lambda: None)
    monkeypatch.setattr(state, "focused_pane", lambda: None)
    monkeypatch.setattr(runtime, "boss_instance", lambda: boss)
    monkeypatch.setattr(runtime, "_state", state)
    collector.write_json(
        tmp_path / "snapshot.json",
        {
            "observed_at": runtime.time(),
            "error": None,
            "panes": [
                {
                    "id": 1,
                    "root_pid": 42,
                    "foreground_pgrp": None,
                    "title": "Task",
                    "cwd": "/work/demo",
                    "label": "demo\nmain",
                    "processes": [],
                }
            ],
        },
    )
    state.refresh()
    state.io_result.result(timeout=2)
    state.refresh()
    state.io_result.result(timeout=2)
    assert redraws == ["update", "dirty", "update", "dirty"]
    assert state.workspaces[1].project == "demo"
    assert json.loads((tmp_path / "panes.json").read_text()) == [
        {
            "id": 1,
            "root_pid": 42,
            "foreground_pgrp": None,
            "title": "Task",
            "cwd": "/start",
        }
    ]

    state.close()
    state.cleanup_thread.join(5)


def test_health_reports_only_supported_agents(monkeypatch):
    monkeypatch.setattr(runtime, "_state", None)
    assert set(runtime.health()) == {"observed_at", "error", "stale"}


def test_collector_uses_root_cwd_when_foreground_process_has_no_directory(
    monkeypatch, tmp_path
):
    monkeypatch.setitem(
        sys.modules, "kitty.child", SimpleNamespace(environ_of_process=lambda pid: {})
    )
    inputs = tmp_path / "panes.json"
    inputs.write_text(
        json.dumps(
            [
                {
                    "id": 1,
                    "root_pid": 42,
                    "cwd": "/resolved-root",
                    "processes": [{"pid": 42, "cmdline": ["sh"], "cwd": None}],
                }
            ]
        )
    )
    (pane,) = collector.collect_panes(inputs)
    assert pane["cwd"] == "/resolved-root"
    assert pane["label"] == "resolved-root"


def test_pane_cache_expires_and_rejects_changed_root_or_foreground(
    monkeypatch, tmp_path
):
    state = runtime.State(None, tmp_path, tmp_path / "worker.py")
    state.observed_at = 100
    state.panes = {
        1: {
            "root_pid": 42,
            "foreground_pgrp": None,
            "cwd": "/demo",
            "processes": [{"pid": 42, "agent": "codex"}],
        }
    }
    monkeypatch.setattr(runtime, "_state", state)
    monkeypatch.setattr(runtime, "time", lambda: 101)
    window = SimpleNamespace(id=1, child=SimpleNamespace(root_pid=42, child_fd=None))
    assert runtime.pane_observation(window)["processes"]
    window.child.root_pid = 43
    assert runtime.pane_observation(window) == {}
    window.child.root_pid = 42
    monkeypatch.setattr(runtime, "time", lambda: 111)
    assert runtime.pane_observation(window) == {}
    monkeypatch.setattr(runtime, "time", lambda: 101)
    window.child.child_fd = 7
    monkeypatch.setattr(runtime.os, "tcgetpgrp", lambda fd: 99)
    assert runtime.pane_observation(window)["processes"] == []


def test_worker_discovers_processes_with_one_scan_per_poll(monkeypatch, tmp_path):
    scans = []

    def process_groups():
        scans.append(True)
        return {20: [20], 30: [30]}

    monkeypatch.setitem(
        sys.modules,
        "kitty.child",
        SimpleNamespace(
            process_group_map=process_groups,
            cmdline_of_pid=lambda pid: ["codex"] if pid == 20 else ["sh"],
            cwd_of_process=lambda pid: None if pid == 30 else f"/work/{pid}",
            environ_of_process=lambda pid: {},
        ),
    )
    inputs = tmp_path / "panes.json"
    inputs.write_text(
        json.dumps(
            [
                {"id": 1, "root_pid": 10, "foreground_pgrp": 20, "cwd": "/start"},
                {"id": 2, "root_pid": 11, "foreground_pgrp": 30, "cwd": "/start"},
            ]
        )
    )
    first, second = collector.collect_panes(inputs)
    assert scans == [True]
    assert first["cwd"] == "/work/20"
    assert first["processes"] == [{"pid": 20, "agent": "codex", "cwd": "/work/20"}]
    assert second["cwd"] == "/work/11"


def test_slow_storage_does_not_block_timer_or_queue_more_work(monkeypatch, tmp_path):
    from threading import Event

    entered = Event()
    release = Event()
    writes = []

    def slow_write(path, panes):
        writes.append(panes)
        entered.set()
        assert release.wait(timeout=5)

    monkeypatch.setattr(collector, "write_json", slow_write)
    boss = SimpleNamespace(all_tabs=[], os_window_map={})
    state = runtime.State(boss, tmp_path, tmp_path / "worker.py")
    monkeypatch.setattr(state, "launch", lambda: None)
    monkeypatch.setattr(state, "focused_pane", lambda: None)
    try:
        state.refresh()
        assert entered.wait(timeout=2)
        pending = state.io_result
        for _ in range(10):
            state.refresh()
        assert state.io_result is pending
        assert not pending.done()
        assert len(writes) == 1
        # Shutdown must also return while the storage thread is blocked.
        state.close()
        assert not pending.done()
    finally:
        release.set()
        state.close()
        state.io_thread.join(timeout=2)
    assert not state.io_thread.is_alive()


def test_close_waits_for_writer_before_removing_private_cache(monkeypatch, tmp_path):
    from threading import Event, Thread

    entered, release = Event(), Event()
    directory = tmp_path / "private"
    directory.mkdir()
    state = runtime.State(None, directory, directory / "worker.py")

    def writer():
        entered.set()
        release.wait(5)
        (directory / "panes.json").write_text("private metadata")

    state.io_thread = Thread(target=writer)
    state.io_thread.start()
    assert entered.wait(2)
    state.close()
    assert directory.exists()
    state.close()
    release.set()
    state.cleanup_thread.join(5)
    assert not state.cleanup_thread.is_alive()
    assert not directory.exists()


@pytest.mark.parametrize("failure", [False, True])
def test_worker_once_reports_collection_errors(monkeypatch, tmp_path, failure):
    monkeypatch.setattr(collector.signal, "signal", lambda *args: None)
    monkeypatch.setattr(collector.signal, "pthread_sigmask", lambda *args: None)
    monkeypatch.setattr(collector, "parent_alive", lambda pid: True)

    def collect(path):
        if failure:
            raise ValueError("invalid input")
        return [{"id": 1}]

    monkeypatch.setattr(collector, "collect_panes", collect)
    output = tmp_path / "snapshot.json"
    collector.run(output, tmp_path / "input.json", 42, once=True)
    snapshot = json.loads(output.read_text())
    assert snapshot["panes"] == ([] if failure else [{"id": 1}])
    assert snapshot["error"] == ("ValueError: invalid input" if failure else None)


def test_worker_cleanup_after_parent_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(collector.signal, "signal", lambda *args: None)
    monkeypatch.setattr(collector.signal, "pthread_sigmask", lambda *args: None)
    monkeypatch.setattr(collector, "parent_alive", lambda pid: False)
    directory = tmp_path / "private"
    directory.mkdir()
    (directory / "panes.json").write_text("private metadata")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worker",
            "--output",
            str(directory / "snapshot.json"),
            "--input",
            str(directory / "panes.json"),
            "--parent",
            "42",
            "--cleanup",
        ],
    )
    collector.main()
    assert not directory.exists()


def test_runtime_start_launch_and_cleanup(monkeypatch, tmp_path):
    import subprocess

    timers = []
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(runtime, "_state", None)
    boss = SimpleNamespace(all_tabs=[])
    monkeypatch.setitem(
        sys.modules,
        "kitty.fast_data_types",
        SimpleNamespace(
            get_boss=lambda: boss, add_timer=lambda *args: timers.append(args)
        ),
    )
    monkeypatch.setitem(
        sys.modules, "kitty.constants", SimpleNamespace(kitty_exe=lambda: "/test/kitty")
    )
    assert runtime.boss_instance() is boss
    state = runtime.start()
    assert runtime.start() is state
    assert timers[0][1:] == (0.5, True)
    calls = []

    class Process:
        def poll(self):
            return None

        def terminate(self):
            calls.append("terminate")

        def wait(self, timeout=None):
            if timeout:
                raise subprocess.TimeoutExpired("kitty", timeout)
            calls.append("wait")

        def kill(self):
            calls.append("kill")

    def launch(command, **kwargs):
        assert command[0:2] == ["/test/kitty", "+runpy"]
        assert "--cleanup" in command
        calls.append("launch")
        return Process()

    monkeypatch.setattr(runtime.subprocess, "Popen", launch)
    state.launch()
    state.launch()
    state.close()
    state.cleanup_thread.join(5)
    state.refresh()
    assert calls == ["launch", "terminate", "kill", "wait"]
    assert not state.directory.exists()


def test_failed_launch_is_throttled(monkeypatch, tmp_path):
    state = runtime.State(None, tmp_path, tmp_path / "worker.py")
    monkeypatch.setattr(runtime, "collector_command", lambda script: ["missing"])
    calls = []

    def launch(*args, **kwargs):
        calls.append(1)
        raise OSError("missing executable")

    monkeypatch.setattr(runtime.subprocess, "Popen", launch)
    state.launch()
    state.launch()
    assert calls == [1]
    assert state.error == "missing executable"


def test_worker_entrypoint(monkeypatch):
    import runpy
    from pathlib import Path

    calls = []
    monkeypatch.setattr(collector, "main", lambda: calls.append(True))
    runpy.run_path(
        str(Path(collector.__file__).with_name("worker.py")), run_name="__main__"
    )
    assert calls == [True]


def test_arguments_and_unrelated_processes_never_reach_snapshot(monkeypatch, tmp_path):
    from kitty_workspaces.agents import AgentAdapter

    adapter = AgentAdapter(
        "wrapped", (), matches_command=lambda cmd: cmd[:2] == ["node", "agent.js"]
    )
    monkeypatch.setattr(collector.agents, "ADAPTERS", (adapter,))
    monkeypatch.setitem(
        sys.modules,
        "kitty.child",
        SimpleNamespace(
            process_group_map=lambda: {10: [10, 20]},
            cmdline_of_pid=lambda pid: (
                ["node", "agent.js", "--token", "AGENT_SECRET"]
                if pid == 20
                else ["curl", "--header", "OTHER_SECRET"]
            ),
            cwd_of_process=lambda pid: "/project",
            environ_of_process=lambda pid: pytest.fail("unnecessary environment read"),
        ),
    )
    inputs = tmp_path / "panes.json"
    inputs.write_text(json.dumps([{"id": 1, "root_pid": 10, "foreground_pgrp": 10}]))
    panes = collector.collect_panes(inputs)
    output = tmp_path / "snapshot.json"
    collector.write_json(output, {"panes": panes})
    assert panes[0]["processes"] == [{"pid": 20, "agent": "wrapped", "cwd": "/project"}]
    assert panes[0]["cwd"] == "/project"
    serialized = output.read_text()
    for private in ("AGENT_SECRET", "OTHER_SECRET", "cmdline", "curl", "agent.js"):
        assert private not in serialized
    assert output.stat().st_mode & 0o777 == 0o600
