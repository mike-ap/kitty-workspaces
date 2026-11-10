# Contributing

For bug reports, include your operating system, Kitty and agent versions, the
project version or checkout revision, and steps to reproduce the problem.
Describe the expected result and the result you observed, with the relevant
configuration and logs.

## Local checks

Enter `devenv shell` (or allow direnv) for Python 3.12, uv, just, ShellCheck,
shfmt, markdownlint-cli2, and Lefthook. Shell entry installs the Git pre-commit
hook, which runs `just check` against the whole checkout. Commit from this
environment so all tools are on PATH. Outside devenv, install those tools and run
`lefthook install` once after cloning.

```sh
uv sync --locked
just check
```

`just check` verifies Python, shell, and Markdown formatting, runs Ruff, ShellCheck, and
markdownlint-cli2, then runs the tests. CI runs the same command on branch pushes,
pull requests, and release tags. The pre-commit hook checks without rewriting
files; use `just format` to apply Python, shell, and Markdown formatting and fixes.
Markdown formatting uses uv-managed mdformat with GitHub Markdown support on the
root-level `*.md` documentation files.
Shell formatting follows `.editorconfig`; Markdown rules live in
`.markdownlint-cli2.jsonc`, which the Neovim markdownlint-cli2 integration also reads.

Install Git on PATH for repository detection tests, which create real temporary
repositories, linked worktrees, submodules, and bare repositories. No remote
repositories or credentials are used.

Install Kitty on PATH to include the runtime checks under Kitty's interpreter.
Those checks are skipped when Kitty is unavailable.

Changes to rendering, pane discovery, or navigation should also pass the isolated
graphical tests. On Linux, install Kitty and Xvfb, then run:

```sh
xvfb-run -a uv run --locked pytest -q --run-kitty-integration -m kitty_integration tests/integration
```

macOS support is experimental. To help validate it, run the pytest command
without `xvfb-run -a` in a Mac desktop session.
The graphical tests use temporary homes and separate Kitty instances. The real
Codex test uses a local model fixture and is skipped if Codex is unavailable.

Python lint rules are explicitly selected in `pyproject.toml`, following
[Astral's rule-selection guidance](https://docs.astral.sh/ruff/linter/#rule-selection).
Both workspace projects use the same stable Ruff rule groups for correctness,
modern Python, imports, simplification, comprehensions, redundant code, return
paths, performance, and precise suppression comments. Preview rules are disabled;
layout is enforced by `ruff format`. Run `uv run --locked ruff check .` to lint
source, scripts, examples (where present), and tests with the locked Ruff version.

## Manual compatibility checks

Use the [README compatibility table](README.md#requirements-and-compatibility)
as the baseline. Before a release or when testing a new dependency version:

1. Record the operating system and the output of `kitty --version`,
   `kitty +runpy 'import sys; print(sys.version)'`, and
   `uv run --locked python --version`. Record versions of agents being tested.
1. Run the local checks with Kitty on PATH and confirm its runtime tests ran.
   Skipped checks do not establish compatibility.
1. Run the graphical suite in the isolated test environment. Check labels,
   focus/navigation, metadata, and configuration reloads. Record which agent
   behavior was tested with fixtures and which used a real installed agent.
1. Install into a temporary Kitty configuration directory and check the installed
   tab-bar hook and metadata endpoint in a separate Kitty instance.
1. Record the revision, commands, and results in the pull request or release
   notes. Update the tested versions in the README only after validation passes.

Validation on Linux does not establish macOS compatibility. Run these checks in
a Mac desktop session before proposing a change to macOS's experimental status.

## Changes

Agent status changes must preserve the boundaries documented under
[agent status](README.md#agent-status). Exercise all five OSC 7501 states, missing
reports, app association, report clearing on focus, and process exit/prompt
cleanup. Verify Kitty's foreground and wrapper-aware root process reporting.
Keep protocol fixtures distinct from real-agent checks and record exact CLI
versions. A passing fixture alone does not establish real-agent compatibility.

Keep changes focused and add regression coverage for behavior changes. Update
the README when configuration or behavior changes, and add user-visible changes
to the Unreleased section of [CHANGELOG.md](CHANGELOG.md).

Preserve the versioned metadata contract used by the companion picker. Breaking
schema or status-meaning changes require a version bump and coordinated picker
updates. Status remains exactly the five OSC 7501 states or null. For contract
changes, also run `just check` in the sibling `kitty-workspace-picker` checkout
and try both projects together; provider-only tests do not exercise the picker's
validation and rendering.

## Adding an agent CLI

Built-in integrations are registered in `src/kitty_workspaces/agents.py` as
`AgentAdapter` instances. Add an entry to `ADAPTERS`; no collector, workspace,
or status changes should be needed for a new CLI.

```python
AgentAdapter(
    id="example",
    executables=("example", "example-preview"),
    status_app="example-cli",
)
```

- `id` is a unique, stable identifier exposed in session metadata.
- `executables` matches the basename of the foreground command's executable.
  For wrappers or command patterns, supply a pure `matches_command(cmdline)`
  callback instead. It replaces executable matching and must handle empty lists.
  The first matching adapter wins; keep matches narrow to avoid other programs.
  Matching runs only in the worker; the UI receives the registered agent ID.
- `status_app` is the native OSC 7501 app name. Leave it `None` when unsupported:
  identification and titles still work, but activity remains Unknown.
- `normalize_title(title, cwd)` optionally cleans terminal titles and returns a
  descriptive string or `None`. The default strips surrounding whitespace.
- `exclude_environment(environment)` optionally identifies tool subprocesses.
  Only matching candidates with this callback have their environments read,
  exclusively in the collector worker. Excluded processes are omitted from the
  snapshot; environments and command arguments are never persisted.

Keep CLI-specific callbacks in a small module beside `agents.py`, following
`claude.py` and `codex.py`. Callbacks must perform no I/O, retain no environments,
and depend on neither Kitty objects nor UI state. Do not infer activity from
terminal titles or introduce screen parsing, hooks, session files, or API polling.
Status interpretation and urgency, workspace naming, and session ordering remain
shared. Changes to process exclusion take effect on the next collector poll;
native status reports are read live.

Add tests for executable aliases or wrappers, title normalization, unrelated
commands, and any subprocess exclusion. Verify native app association and missing
reports; `tests/test_agents.py` demonstrates an additional adapter flowing through
collection and session assembly. Run the local and graphical checks above, and
document tested CLI versions and native protocol limitations in the README.
Adapters are built into the package; external plugin discovery is not supported.

## Release preparation

Source archives are the supported release artifact. Keep changelog entries under
Unreleased until preparing a release. Set the version in `pyproject.toml`, update
the lockfile with `uv lock`, and move the release's changelog entries into a dated
version section. Run the checks and manual compatibility checks above, then:

```sh
just dist
```

This runs `uv build --sdist` and
`uv run --locked python scripts/check_dist.py`, producing and verifying
`dist/kitty_workspaces-VERSION.tar.gz`. Kitty and uv must be on PATH. The check
compares the archive with the checkout, extracts it outside the checkout,
installs into a temporary Kitty configuration from an unrelated directory,
checks that existing configuration survives, and loads the installed package
and entry points under Kitty's interpreter. It also checks the collector's
command-line startup. Unlike optional runtime tests, release verification fails
if Kitty is unavailable.

Use a dated changelog heading exactly like `## 0.1.0 - 2026-11-04`. Commit the
prepared source, then run:

```sh
just release 0.1.0
```

`just release VERSION` validates the version and dated notes, requires a clean
checkout on a branch with an `origin` remote, and rejects an existing local or
remote tag. It runs `just check` and `just dist`, creates an annotated `vVERSION`
tag, then atomically pushes the current branch and tag to `origin`. It does not
bump versions, edit the changelog, or make commits. Complete manual compatibility
checks before running it. If the push fails, the local tag remains; resolve the
reported problem and push the branch and tag together, or delete the local tag
before retrying the command.

The tag-triggered `.github/workflows/release.yml` installs Kitty 0.50.0, runs the
checks, builds and verifies the source archive, and validates that the stable
`vMAJOR.MINOR.PATCH` tag matches `pyproject.toml` and has dated changelog notes.
The release workflow also runs the graphical suite; the regular branch/PR
workflow runs `just check` and coverage but does not run graphical tests.
A separate publishing job creates the GitHub release only after verification.
Manual compatibility checks still happen before tagging. Prereleases are not
supported by this workflow.

Release assets are the source archive (with a stable project-based filename),
`SHA256SUMS`, and `bootstrap.sh`. The workflow renders the bootstrap template with
`github.repository` and the release tag. Thus the permanent
`releases/latest/download/bootstrap.sh` URL installs a complete, pinned release
without mixing files from different releases. `--version VERSION` selects an
older release; rerunning the default URL updates to the latest published release.
The download step uses the same `install.sh` verified by `just dist`.

No credentials or GitHub CLI are required on users' machines.
Rebuild and verify after any source or documentation change. Wheel/PyPI
publishing is deferred. The metadata protocol version is independent of the
project release version.

## License

Contributions are made under the project's [MIT license](LICENSE).

## Coverage

Run `just coverage` for branch-inclusive terminal, XML (`coverage.xml`), and
HTML (`htmlcov/index.html`) reports. CI uploads these reports as the `coverage`
artifact. Coverage measures Python in pytest, including runpy entry points;
separate Kitty processes and shell installers are exercised by tests but are
not instrumented. Missing lines remain visible; no coverage exclusions hide
Kitty entry points.
