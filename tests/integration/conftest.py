import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep

import pytest

FIXTURES = Path(__file__).resolve().parent
REPOSITORY = FIXTURES.parents[1]


@dataclass
class KittyTerminal:
    kitty: str
    process: subprocess.Popen
    env: dict
    socket: str
    config: Path
    project: Path
    log: Path
    last_snapshot: dict = field(default_factory=dict)

    def command(self, *args, check=True):
        return subprocess.run(
            [
                self.kitty,
                "@",
                "--to",
                self.socket,
                "--use-password",
                "never",
                *map(str, args),
            ],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=10,
            check=check,
        )

    def state(self):
        return json.loads(self.command("ls").stdout)

    def snapshot(self):
        self.last_snapshot = json.loads(
            self.command("kitten", FIXTURES / "probe.py").stdout
        )
        return self.last_snapshot

    def wait_for(self, predicate, description, timeout=10):
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            assert self.process.poll() is None, (
                f"Kitty exited. Log ({self.log}): {self.log.read_text()}"
            )
            result = predicate()
            if result:
                return result
            sleep(0.05)
        pytest.fail(
            f"Timed out waiting for {description}. "
            f"Last screen: {self.last_snapshot!r}. Kitty log ({self.log}): {self.log.read_text()}"
        )

    def wait_label(self, tab_id, expected):
        return self.wait_for(
            lambda: self.snapshot()["labels"].get(str(tab_id)) == expected,
            f"tab {tab_id} to render {expected!r}",
        )

    def tab_for_window(self, window_id):
        return next(
            tab["id"]
            for os_window in self.state()
            for tab in os_window["tabs"]
            if any(window["id"] == window_id for window in tab["windows"])
        )

    def launch_agent(self, title, status="idle", kind="tab", session_name=None):
        result = self.command(
            "launch",
            "--type",
            kind,
            "--cwd",
            self.project,
            sys.executable,
            FIXTURES / "agent.py",
            title,
            status,
            *([session_name] if session_name is not None else []),
        )
        window_id = int(result.stdout)
        self.wait_for(
            lambda: (
                f"READY {title}"
                in self.command("get-text", "--match", f"id:{window_id}").stdout
            ),
            f"fixture session {title}",
        )
        return self.tab_for_window(window_id), window_id


@pytest.fixture
def terminal(tmp_path):
    kitty = shutil.which("kitty")
    if kitty is None:
        pytest.fail("Kitty must be on PATH to run integration tests")
    if sys.platform != "darwin" and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        pytest.fail(
            "A display is required; on Linux use xvfb-run -a just test-integration"
        )

    home = tmp_path / "home"
    config = home / ".config" / "kitty"
    config.mkdir(parents=True)
    source = tmp_path / "dotfiles" / "tab_bar.py"
    source.parent.mkdir()
    source.write_text("# Dotfile-manager source; keep the symlink intact.\n")
    (config / "tab_bar.py").symlink_to(source)
    subprocess.run(
        [
            "sh",
            str(REPOSITORY / "install.sh"),
            "--source-dir",
            str(REPOSITORY),
            "--config-dir",
            str(config),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    source.write_text((REPOSITORY / "examples/tab_bar.py").read_text())
    project = tmp_path / "demo"
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(project)],
        check=True,
        capture_output=True,
        timeout=10,
    )
    settings = [
        # The harness uses only its private socket; panes get no control access.
        "allow_remote_control socket-only",
        "watcher kitty_workspaces/watcher.py",
        "tab_bar_min_tabs 1",
        "tab_bar_edge left",
        "tab_bar_style separator",
        "tab_title_max_lines 2",
        "tab_title_max_length 40",
        'tab_title_template "{custom}"',
        'active_tab_title_template "{custom}"',
        "confirm_os_window_close 0",
        "enable_audio_bell no",
        "update_check_interval 0",
        "shell_integration disabled",
        "remember_window_size no",
        "font_size 11",
        "initial_window_width 1000",
        "initial_window_height 600",
    ]
    if sys.platform != "darwin":
        backend = "x11" if os.environ.get("DISPLAY") else "wayland"
        settings.append(f"linux_display_server {backend}")
    (config / "kitty.conf").write_text("\n".join(settings) + "\n")

    env = {
        key: value for key, value in os.environ.items() if not key.startswith("KITTY_")
    }
    env.update(
        HOME=str(home),
        CODEX_HOME=str(home / ".codex"),
        PATH=os.environ["PATH"],
        KITTY_CONFIG_DIRECTORY=str(config),
        XDG_CONFIG_HOME=str(home / ".config"),
        XDG_CACHE_HOME=str(home / ".cache"),
        XDG_DATA_HOME=str(home / ".local/share"),
    )
    # macOS limits Unix socket paths to roughly 100 bytes; /tmp stays short.
    with TemporaryDirectory(prefix="kat-", dir="/tmp") as socket_dir:
        socket = f"unix:{socket_dir}/control"
        log = tmp_path / "kitty.log"
        with log.open("w") as output:
            process = subprocess.Popen(
                [
                    kitty,
                    "--config",
                    str(config / "kitty.conf"),
                    "--listen-on",
                    socket,
                    "--directory",
                    str(project),
                    sys.executable,
                    str(FIXTURES / "agent.py"),
                    "Alpha",
                    "idle",
                ],
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
            instance = KittyTerminal(kitty, process, env, socket, config, project, log)
            try:
                instance.wait_for(
                    lambda: instance.command("ls", check=False).returncode == 0,
                    "Kitty's private control socket",
                    timeout=15,
                )
                instance.wait_for(
                    lambda: "Alpha" in "\n".join(instance.snapshot()["rows"]),
                    "the initial fixture label",
                )
                yield instance
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
