import os
import shutil
import subprocess
import sys
from time import monotonic

import pytest

from kitty_workspaces import worktrees


def git(root, *arguments):
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    return (
        subprocess.run(
            ["git", "-C", str(root), *map(str, arguments)],
            env=env,
            check=True,
            capture_output=True,
            timeout=10,
        )
        .stdout.decode()
        .removesuffix("\n")
    )


def init(root, branch="main", *options):
    root.mkdir(parents=True)
    git(root, "init", f"--initial-branch={branch}", *options)
    return root


def commit(root):
    git(
        root,
        "-c",
        "user.name=Test Author",
        "-c",
        "user.email=test@example.invalid",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--allow-empty",
        "-m",
        "Initial commit",
    )
    return git(root, "rev-parse", "HEAD")


def linked(root, target, branch="feature/raw"):
    commit(root)
    git(root, "worktree", "add", "-b", branch, target)
    return target


def test_ordinary_repository_uses_branch_from_nested_directory(tmp_path):
    root = init(tmp_path / "demo", "feature/sidebar")
    nested = root / "src"
    nested.mkdir()
    assert worktrees.label(str(nested), 0) == "demo\nsidebar"
    assert worktrees.context(str(nested), 0) == (
        str(root),
        str(root),
        "feature/sidebar",
    )


@pytest.mark.parametrize("relative", [False, True])
def test_separate_git_directory_uses_project_instead_of_metadata(tmp_path, relative):
    storage = tmp_path / "metadata"
    root = init(tmp_path / "project", "feature/raw", "--separate-git-dir", storage)
    if relative:
        (root / ".git").write_text("gitdir: ../metadata\n")
    nested = root / "src"
    nested.mkdir()
    assert worktrees.label(str(nested), 0) == "project\nraw"
    assert worktrees.context(str(nested), 0) == (str(root), str(root), "feature/raw")


@pytest.mark.parametrize("separator", ["-", ".", "_"])
def test_linked_worktree_uses_worktree_name_and_main_repository(tmp_path, separator):
    main = init(tmp_path / "demo")
    root = linked(main, tmp_path / f"demo{separator}task")
    nested = root / "src"
    nested.mkdir()
    assert worktrees.label(str(nested), 0) == "demo\ntask"
    assert worktrees.context(str(nested), 0) == (str(main), str(root), "feature/raw")


def test_branch_prefix_setting_refreshes_labels(monkeypatch, tmp_path):
    config = tmp_path / "kitty_workspaces.toml"
    monkeypatch.setattr(worktrees, "CONFIG", config)
    root = init(tmp_path / "demo", "hotfix/login")
    assert worktrees.label(str(root), 0) == "demo\nlogin"
    for refresh, value, expected in (
        (1, "false", "hotfix/login"),
        (2, "true", "login"),
        (3, '"false"', "login"),
        (4, "invalid toml", "login"),
    ):
        config.write_text(f"strip_branch_prefix = {value}\n")
        assert worktrees.label(str(root), refresh) == f"demo\n{expected}"
        assert worktrees.context(str(root), refresh)[2] == "hotfix/login"


@pytest.mark.parametrize("name", ["1234567", "demo-1234567", "demo-8675309-abcdef"])
def test_generated_worktree_names_fall_back_to_branch(monkeypatch, tmp_path, name):
    config = tmp_path / "kitty_workspaces.toml"
    config.write_text("strip_branch_prefix = false\n")
    monkeypatch.setattr(worktrees, "CONFIG", config)
    main = init(tmp_path / "demo")
    root = linked(main, tmp_path / name, "chore/deps")
    assert worktrees.label(str(root), 0) == "demo\nchore/deps"


@pytest.mark.parametrize("linked_worktree", [False, True])
def test_detached_head_keeps_roots_and_uses_short_revision(tmp_path, linked_worktree):
    main = init(tmp_path / "demo")
    if linked_worktree:
        root = linked(main, tmp_path / "demo-1234567")
        revision = git(root, "rev-parse", "HEAD")
    else:
        root = main
        revision = commit(root)
    git(root, "checkout", "--detach", revision)
    assert worktrees.context(str(root), 0) == (str(main), str(root), None)
    assert worktrees.label(str(root), 0) == f"demo\n{revision[:7]}"


@pytest.mark.parametrize("nested", [False, True])
def test_bare_repository_context_and_label(tmp_path, nested):
    root = init(tmp_path / "demo.git", "feature/raw", "--bare")
    cwd = root / "objects" if nested else root
    assert worktrees.context(str(cwd), 0) == (str(root), None, "feature/raw")
    assert worktrees.label(str(cwd), 0) == "demo\nraw"


@pytest.mark.parametrize("invalid", ["objects", "refs", "HEAD", "not_bare"])
def test_bare_repository_lookalikes_are_not_worktrees(tmp_path, invalid):
    root = init(tmp_path / "demo.git", "main", "--bare")
    if invalid == "HEAD":
        (root / "HEAD").write_text("not a git head\n")
    elif invalid == "not_bare":
        git(root, "config", "core.bare", "false")
    else:
        shutil.rmtree(root / invalid)
    assert worktrees.context(str(root), 0) == (None, None, None)
    assert worktrees.label(str(root), 0) == "demo.git"


@pytest.mark.parametrize(
    "variant",
    [
        "[core]\n bare = true\n",
        "[core]\n bare\n",
        "[core]\n bare = true # bare repository\n",
        "[core]\n bare = true ; bare repository\n",
        "[custom]\n enabled\n",
    ],
)
def test_bare_repository_uses_git_config_semantics(tmp_path, variant):
    root = init(tmp_path / "demo.git", "main", "--bare")
    config = root / "config"
    config.write_text(config.read_text() + variant)
    assert worktrees.context(str(root), 0) == (str(root), None, "main")


def test_bare_repository_named_dot_git_and_linked_worktree(tmp_path):
    parent = tmp_path / "demo"
    common = init(parent / ".git", "main", "--bare")
    for cwd in (parent, common, common / "objects"):
        assert worktrees.context(str(cwd), 0) == (str(common), None, "main")
        assert worktrees.label(str(cwd), 0) == "demo\nmain"
    root = tmp_path / "demo-task"
    git(common, "worktree", "add", "--orphan", "-b", "task", root)
    assert worktrees.context(str(root), 0) == (str(common), str(root), "task")
    assert worktrees.label(str(root), 0) == "demo\ntask"


def test_linked_worktree_backed_by_bare_repository(tmp_path):
    common = init(tmp_path / "demo.git", "main", "--bare")
    root = tmp_path / "demo-task"
    git(common, "worktree", "add", "--orphan", "-b", "feature/raw", root)
    assert worktrees.context(str(root), 0) == (str(common), str(root), "feature/raw")
    assert worktrees.label(str(root), 0) == "demo\ntask"


def test_non_bare_project_name_keeps_dot_git_suffix_in_linked_worktree(tmp_path):
    main = init(tmp_path / "demo.git")
    root = linked(main, tmp_path / "demo.git-task")
    assert worktrees.label(str(root), 0) == "demo.git\ntask"


def test_submodule_uses_its_checkout_name_instead_of_git_storage(tmp_path):
    origin = init(tmp_path / "origin")
    commit(origin)
    parent = init(tmp_path / "parent")
    git(
        parent,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        origin,
        "modules/widget",
    )
    root = parent / "modules" / "widget"
    assert worktrees.context(str(root), 0) == (str(root), str(root), "main")
    assert worktrees.label(str(root), 0) == "widget\nmain"


def test_linked_worktree_with_external_metadata_uses_git_reported_repository(tmp_path):
    storage = tmp_path / "metadata"
    main = init(tmp_path / "project", "main", "--separate-git-dir", storage)
    root = linked(main, tmp_path / "task")
    # Git stores no back pointer to the separate main checkout in this layout.
    assert worktrees.context(str(root), 0) == (str(storage), str(root), "feature/raw")


def test_paths_with_whitespace_and_quotes_are_not_split(tmp_path):
    main = init(tmp_path / 'demo "quoted"\nname\r')
    root = linked(main, tmp_path / 'task with\nnewlines\rand "quotes"')
    assert worktrees.context(str(root), 0) == (str(main), str(root), "feature/raw")
    assert (
        worktrees.label(str(root), 0)
        == 'demo "quoted"name\ntask withnewlinesand "quotes"'
    )


def test_inherited_git_environment_does_not_override_pane_directory(
    monkeypatch, tmp_path
):
    main = init(tmp_path / "demo", "feature/raw")
    other = init(tmp_path / "other")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    assert worktrees.context(str(main), 0) == (str(main), str(main), "feature/raw")


def test_labels_and_context_share_cache_and_refresh_after_branch_change(
    monkeypatch, tmp_path
):
    root = init(tmp_path / "demo", "main")
    original = worktrees.subprocess.run
    calls = []

    def run(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(worktrees.subprocess, "run", run)
    for _ in range(2):
        assert worktrees.label(str(root), 0) == "demo\nmain"
        assert worktrees.context(str(root), 0)[2] == "main"
    assert len(calls) == 3
    git(root, "symbolic-ref", "HEAD", "refs/heads/feature/new")
    assert worktrees.label(str(root), 0) == "demo\nmain"
    calls.clear()
    assert worktrees.context(str(root), 1)[2] == "feature/new"
    assert worktrees.label(str(root), 1) == "demo\nnew"
    assert len(calls) == 3


def test_unavailable_git_falls_back_and_recovers_next_bucket(monkeypatch, tmp_path):
    root = init(tmp_path / "demo")
    original_path = os.environ["PATH"]
    monkeypatch.setenv("PATH", str(tmp_path / "no-programs"))
    assert worktrees.label(str(root), 0) == "demo"
    assert worktrees.context(str(root), 0) == (None, None, None)
    monkeypatch.setenv("PATH", original_path)
    assert worktrees.context(str(root), 1) == (str(root), str(root), "main")


def test_stalled_git_is_terminated_within_lookup_deadline(monkeypatch, tmp_path):
    binary = tmp_path / "git"
    binary.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(60)\n")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(worktrees, "GIT_TIMEOUT", 0.05)
    started = monotonic()
    assert worktrees.label(str(tmp_path), 0) == tmp_path.name
    assert worktrees.context(str(tmp_path), 0) == (None, None, None)
    assert monotonic() - started < 2


def test_non_repository_and_missing_directory_fall_back(tmp_path):
    for cwd in (tmp_path, tmp_path / "missing"):
        assert worktrees.context(str(cwd), 0) == (None, None, None)
        assert worktrees.label(str(cwd), 0) == cwd.name


def test_directories_share_repository_worktree_listing(monkeypatch, tmp_path):
    root = init(tmp_path / "demo")
    directories = [root / str(i) for i in range(10)]
    for directory in directories:
        directory.mkdir()
    original = worktrees.subprocess.run
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return original(command, **kwargs)

    monkeypatch.setattr(worktrees.subprocess, "run", run)
    for directory in directories:
        assert worktrees.context(str(directory), 0) == (str(root), str(root), "main")
    assert len(commands) == 21
    assert sum("list" in command for command in commands) == 1
