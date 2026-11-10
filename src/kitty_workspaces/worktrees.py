"""Cached Git queries for labels and metadata in the polling worker."""

import os
import re
import subprocess
import tomllib
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from time import monotonic

from .labels import printable

GIT_TIMEOUT = 0.5
_worktree_cache = OrderedDict()
CONFIG = Path(__file__).resolve().parent.parent / "kitty_workspaces.toml"


def strip_branch_prefix():
    try:
        with CONFIG.open("rb") as stream:
            value = tomllib.load(stream).get("strip_branch_prefix", True)
        return value if isinstance(value, bool) else True
    except (OSError, ValueError):
        return True


@dataclass(frozen=True)
class Repository:
    repository: Path
    worktree: Path | None
    branch: str | None
    revision: str
    linked: bool = False
    bare: bool = False


def git(cwd, deadline, *arguments):
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("Git lookup deadline exceeded")
    # The pane's directory determines its repository, not Kitty's launch environment.
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    env["GIT_OPTIONAL_LOCKS"] = "0"
    result = subprocess.run(
        ["git", "-C", str(cwd), *arguments],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        env=env,
        check=True,
        timeout=remaining,
    )
    return os.fsdecode(result.stdout).removesuffix("\n")


def records(output):
    """Parse Git's NUL-delimited porcelain without splitting unusual paths."""
    result = []
    for record in output.split("\0\0"):
        if not record:
            continue
        fields = {}
        for attribute in record.split("\0"):
            key, _, value = attribute.partition(" ")
            fields[key] = value
        result.append(fields)
    return result


def worktree_records(common, refresh, deadline):
    """Share the worktree list across directories and linked checkouts."""
    key = (common, refresh)
    if key not in _worktree_cache:
        _worktree_cache[key] = records(
            git(common, deadline, "worktree", "list", "--porcelain", "-z")
        )
        if len(_worktree_cache) > 256:
            _worktree_cache.popitem(last=False)
    _worktree_cache.move_to_end(key)
    return _worktree_cache[key]


@lru_cache(maxsize=256)
def repository(cwd, refresh):
    """Share one bounded lookup between labels and metadata for each time bucket."""
    deadline = monotonic() + GIT_TIMEOUT
    try:
        bare, inside, common = git(
            cwd,
            deadline,
            "rev-parse",
            "--is-bare-repository",
            "--is-inside-work-tree",
            "--path-format=absolute",
            "--git-common-dir",
        ).split("\n", 2)
        if bare != "true" and inside != "true":
            return None
        common = Path(common).resolve()
        if bare == "true":
            try:
                branch = git(cwd, deadline, "symbolic-ref", "--quiet", "HEAD")
            except subprocess.CalledProcessError as error:
                if error.returncode != 1:
                    raise
                revision = git(cwd, deadline, "rev-parse", "--verify", "HEAD")
                return Repository(common, None, None, revision, bare=True)
            return Repository(
                common, None, branch.removeprefix("refs/heads/"), "", bare=True
            )

        root = Path(git(cwd, deadline, "rev-parse", "--show-toplevel")).resolve()
        worktrees = worktree_records(common, refresh, deadline)
        if not worktrees:
            return None
        main = worktrees[0]
        current = next(
            (item for item in worktrees if Path(item["worktree"]).resolve() == root),
            main,
        )
        linked = current is not main
        # A separate Git directory or submodule may be listed by its storage path.
        # The current main checkout's top level is authoritative in that case.
        if not linked:
            project = root
        elif "bare" in main:
            project = common
        else:
            project = Path(main["worktree"]).resolve()
        branch = current.get("branch")
        return Repository(
            project,
            root,
            branch.removeprefix("refs/heads/") if branch else None,
            current.get("HEAD", ""),
            linked=linked,
            bare="bare" in main,
        )
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
    ):
        return None


def worktree_name(info, project, strip_prefix):
    branch = info.branch or info.revision[:7] or "detached"
    if info.branch and strip_prefix:
        branch = re.sub(r"^(feature|fix|bugfix|hotfix|chore)/", "", branch)
    if not info.linked:
        return branch
    name = info.worktree.name
    for separator in (".", "-", "_"):
        prefix = project + separator
        if name.startswith(prefix):
            name = name.removeprefix(prefix)
            break
    return branch if re.fullmatch(r"[0-9a-fA-F-]{7,}|\d+", name) else name


@lru_cache(maxsize=256)
def label(cwd, refresh):
    info = repository(cwd, refresh)
    if info is None:
        return fallback_label(cwd)
    project = info.repository.name
    if info.bare:
        project = project.removesuffix(".git") or info.repository.parent.name
    name = worktree_name(info, project, strip_branch_prefix())
    return f"{printable(project)}\n{printable(name)}"


def context(cwd, refresh):
    """Return filesystem identities and an unshortened branch independently of labels."""
    info = repository(cwd, refresh)
    if info is None:
        return None, None, None
    return (
        str(info.repository),
        str(info.worktree) if info.worktree else None,
        info.branch,
    )


def fallback_label(cwd):
    """Directory-only fallback with no filesystem access."""
    directory = Path(cwd)
    return printable(directory.name or str(directory))
