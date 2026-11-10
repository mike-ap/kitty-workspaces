"""Catch imports that work in uv's Python but fail inside Kitty."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_modules_import_with_kitty_python():
    kitty = shutil.which("kitty")
    if kitty is None:
        pytest.skip("Kitty is not installed")

    source = Path(__file__).resolve().parents[1] / "src"
    code = (
        "import sys; "
        "sys.path.insert(0, sys.argv[1]); "
        "from kitty_workspaces import tab_bar; "
        "assert tab_bar.get_boss is not None"
    )
    result = subprocess.run(
        [kitty, "+runpy", code, str(source)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("symlinked", [False, True])
def test_installed_hook_loads_with_kitty_python(tmp_path, symlinked):
    kitty = shutil.which("kitty")
    if kitty is None:
        pytest.skip("Kitty is not installed")

    if symlinked:
        source = tmp_path / "dotfiles.py"
        source.write_text("# Managed by a dotfile manager\n")
        (tmp_path / "tab_bar.py").symlink_to(source)

    installer = Path(__file__).resolve().parents[1] / "install.sh"
    subprocess.run(
        [
            "sh",
            str(installer),
            "--source-dir",
            str(installer.parent),
            "--config-dir",
            str(tmp_path),
        ],
        check=True,
    )
    # Enabling tab names is now an explicit manual configuration step.
    (tmp_path / "tab_bar.py").write_text(
        (installer.parent / "examples/tab_bar.py").read_text()
    )
    code = (
        "import runpy, sys; from pathlib import Path; "
        "config = Path(sys.argv[1]); "
        "hook = runpy.run_path(str(config / 'tab_bar.py')); "
        "bar = hook['kitty_workspaces'].tab_bar; "
        "assert Path(bar.__file__).parent == config / 'kitty_workspaces'; "
    )
    result = subprocess.run(
        [kitty, "+runpy", code, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_title_layout_with_real_kitty_options():
    kitty = shutil.which("kitty")
    if kitty is None:
        pytest.skip("Kitty is not installed")

    source = Path(__file__).resolve().parents[1] / "src"
    code = r"""
import sys
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
from kitty.fast_data_types import LEFT_EDGE, RIGHT_EDGE, TOP_EDGE, BOTTOM_EDGE
from kitty.options.types import Options
from kitty_workspaces import tab_bar

options = Options()
tab_bar.get_options = lambda: options
tab_bar.get_boss = lambda: SimpleNamespace(tab_for_id=lambda tab_id: None)
data = {"tab_id": 1, "title": "demo\nTask", "max_title_length": 40}
for edge in (LEFT_EDGE, RIGHT_EDGE, TOP_EDGE, BOTTOM_EDGE):
    options.tab_bar_edge = edge
    for line_limit in (1, 2):
        options.tab_title_max_lines = line_limit
        vertical = edge in (LEFT_EDGE, RIGHT_EDGE) and line_limit >= 2
        expected = " demo \n Task " if vertical else " demo · Task "
        assert tab_bar.draw_title(data) == expected
"""
    result = subprocess.run(
        [kitty, "+runpy", code, str(source)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_kitten_endpoint_uses_canonical_runtime():
    kitty = shutil.which("kitty")
    if kitty is None:
        pytest.skip("Kitty is not installed")
    source = Path(__file__).resolve().parents[1] / "src"
    code = r"""
import json, runpy, sys
from pathlib import Path
from types import SimpleNamespace
source = Path(sys.argv[1])
sys.path.insert(0, str(source))
from kitty_workspaces import runtime
from kitty import fast_data_types
fast_data_types.add_timer = lambda *args: 123
boss = SimpleNamespace(all_tabs=[])
state = runtime.start(boss)
assert runtime.start(boss) is state
endpoint = str(source / "kitty_workspaces/kitten.py")
handler = runpy.run_path(endpoint)['handle_result']
for _ in range(2):
    result = json.loads(handler([endpoint, 'state'], None, 0, boss))
    assert result['version'] == 1 and result['workspaces'] == []
    assert runtime.current() is state
health = json.loads(handler([endpoint, 'health'], None, 0, boss))
assert health['stale']
try:
    handler([endpoint, 'invalid'], None, 0, boss)
except ValueError:
    pass
else:
    raise AssertionError('invalid command accepted')
"""
    result = subprocess.run(
        [kitty, "+runpy", code, str(source)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_installed_collector_uses_kitty_without_system_python(
    tmp_path,
):
    kitty = shutil.which("kitty")
    if kitty is None:
        pytest.skip("Kitty is not installed")
    import os

    installer = Path(__file__).resolve().parents[1] / "install.sh"
    subprocess.run(
        [
            "sh",
            str(installer),
            "--source-dir",
            str(installer.parent),
            "--config-dir",
            str(tmp_path),
        ],
        check=True,
    )
    code = r"""
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from kitty_workspaces.runtime import collector_command
from kitty.program_status import ProgramStatus
from kitty_workspaces.status import reported_status
from types import SimpleNamespace
ps = ProgramStatus()
ps.handle_escape_code(b'state=working:app=codex')
assert reported_status(SimpleNamespace(program_status=ps), 'codex') == 'working'
assert 'websockets' not in sys.modules
command = collector_command(Path(sys.argv[1])/'kitty_workspaces/worker.py')
assert command[1] == '+runpy'
assert command[0].endswith('kitty')
print("ok")
"""
    env = {
        **os.environ,
        "PATH": str(tmp_path),
        "CODEX_HOME": str(tmp_path / "no-server"),
    }
    result = subprocess.run(
        [kitty, "+runpy", code, str(tmp_path)],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_collector_unblocks_inherited_termination_signal(tmp_path):
    import json
    import os
    from time import monotonic, sleep

    kitty = shutil.which("kitty")
    if kitty is None:
        pytest.skip("Kitty is not installed")
    source = Path(__file__).resolve().parents[1] / "src"
    output = tmp_path / "snapshot.json"
    panes = tmp_path / "panes.json"
    panes.write_text("[]")
    bootstrap = (
        "import runpy, signal, sys; "
        "signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM}); "
        "sys.path.insert(0, sys.argv[1]); sys.argv = sys.argv[2:]; "
        'runpy.run_path(sys.argv[0], run_name="__main__")'
    )
    process = subprocess.Popen(
        [
            kitty,
            "+runpy",
            bootstrap,
            str(source),
            str(source / "kitty_workspaces/worker.py"),
            "--output",
            str(output),
            "--input",
            str(panes),
            "--parent",
            str(os.getpid()),
        ],
        env={
            **os.environ,
            "PATH": str(tmp_path),
            "CODEX_HOME": str(tmp_path / "no-server"),
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = monotonic() + 5
        while not output.exists() and process.poll() is None and monotonic() < deadline:
            sleep(0.02)
        assert output.exists(), process.communicate(timeout=1)[1].decode()
        assert "panes" in json.loads(output.read_text())
        process.terminate()
        process.wait(timeout=4)
        assert process.returncode == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)


def test_native_program_status_lifecycle_with_kitty():
    kitty = shutil.which("kitty")
    if kitty is None:
        pytest.skip("Kitty is not installed")
    source = Path(__file__).resolve().parents[1] / "src"
    code = r"""
import sys
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
from kitty.program_status import ProgramStatus
from kitty_workspaces.status import reported_status
ps = ProgramStatus()
w = SimpleNamespace(program_status=ps)
for agent, app in [('claude', 'claude-code'), ('codex', 'codex')]:
    ps.clear()
    for state in ('idle', 'working', 'blocked', 'error', 'done'):
        ps.handle_escape_code(f'state={state}:app={app}'.encode())
        assert reported_status(w, agent) == state
    ps.on_seen_by_user()
    assert reported_status(w, agent) is None
    ps.handle_escape_code(f'state=working:app={app}'.encode())
    ps.handle_escape_code(b'state=blocked:id=tool:kind=permission')
    assert reported_status(w, agent) == 'blocked'
    ps.on_process_exit_or_prompt()
    assert reported_status(w, agent) is None
"""
    result = subprocess.run(
        [kitty, "+runpy", code, str(source)], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr
