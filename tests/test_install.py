import subprocess
from pathlib import Path
from shutil import copy2, copytree

INSTALLER = Path(__file__).resolve().parents[1] / "install.sh"


def install(config_dir):
    return subprocess.run(
        [
            "sh",
            str(INSTALLER),
            "--config-dir",
            str(config_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_install_is_repeatable_and_leaves_kitty_conf_alone(tmp_path):
    config = tmp_path / "kitty"
    config.mkdir()
    original = "tab_bar_style powerline\nmap ctrl+shift+p next_tab\n"
    (config / "kitty.conf").write_text(original)
    (config / "tab_bar.py").write_text(
        "def draw_title(data):\n    return data['title']\n"
    )

    assert install(config).returncode == 0
    installed_hook = (config / "tab_bar.py").read_text()
    assert install(config).returncode == 0
    assert (config / "tab_bar.py").read_text() == installed_hook
    assert (config / "kitty.conf").read_text() == original
    assert installed_hook == "def draw_title(data):\n    return data['title']\n"
    assert (config / "kitty_workspaces" / "__init__.py").is_file()
    assert (config / "kitty_workspaces" / "tab_bar.py").is_file()


def test_install_preserves_symlink_chain_to_writable_tab_bar(tmp_path):
    config = tmp_path / "kitty"
    config.mkdir()
    source = tmp_path / "dotfiles" / "tab_bar.py"
    source.parent.mkdir()
    original = "def draw_title(data):\n    return data['title']\n"
    source.write_text(original)
    intermediate = tmp_path / "managed-link.py"
    intermediate.symlink_to(source)
    bar = config / "tab_bar.py"
    bar.symlink_to(intermediate)

    assert install(config).returncode == 0
    installed = source.read_text()
    assert install(config).returncode == 0

    assert bar.is_symlink()
    assert intermediate.is_symlink()
    assert source.read_text() == installed
    assert installed.startswith(original)
    assert installed == original
    assert (config / "kitty_workspaces" / "claude.py").is_file()


def test_install_ignores_dangling_tab_bar_symlink(tmp_path):
    config = tmp_path / "kitty"
    config.mkdir()
    bar = config / "tab_bar.py"
    bar.symlink_to(tmp_path / "missing.py")

    result = install(config)

    assert result.returncode == 0
    assert bar.is_symlink()
    assert not bar.exists()
    assert (config / "kitty_workspaces").is_dir()


def test_reinstall_refreshes_package_and_command_endpoint(tmp_path):
    assert install(tmp_path).returncode == 0
    assert not (tmp_path / "tab_bar.py").exists()
    (tmp_path / "kitty_workspaces" / "workspace.py").write_text("# old version\n")
    (tmp_path / "kitty_workspaces/kitten.py").write_text("# old endpoint\n")

    assert install(tmp_path).returncode == 0

    source = INSTALLER.parent / "src"
    for module in (source / "kitty_workspaces").glob("*.py"):
        assert (
            tmp_path / "kitty_workspaces" / module.name
        ).read_bytes() == module.read_bytes()
    assert (tmp_path / "kitty_workspaces/kitten.py").read_bytes() == (
        source / "kitty_workspaces/kitten.py"
    ).read_bytes()
    assert not (tmp_path / "tab_bar.py").exists()


def test_install_finds_local_source_from_unrelated_directory(tmp_path):
    source = tmp_path / "source with spaces"
    source.mkdir()
    copy2(INSTALLER, source / "install.sh")
    copy2(INSTALLER.parent / "pyproject.toml", source / "pyproject.toml")
    copytree(INSTALLER.parent / "src", source / "src")
    copytree(INSTALLER.parent / "config", source / "config")
    config = tmp_path / "config"
    result = subprocess.run(
        ["sh", str(source / "install.sh"), "--config-dir", str(config)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert (config / "kitty_workspaces/kitten.py").is_file()
    assert not (config / "tab_bar.py").exists()
    assert not (config / "kitty.conf").exists()


def test_incomplete_local_source_does_not_create_configuration(tmp_path):
    source = tmp_path / "incomplete"
    source.mkdir()
    copy2(INSTALLER, source / "install.sh")
    copy2(INSTALLER.parent / "pyproject.toml", source / "pyproject.toml")
    config = tmp_path / "config"
    result = subprocess.run(
        ["sh", str(source / "install.sh"), "--config-dir", str(config)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "incomplete source directory" in result.stderr
    assert not config.exists()
