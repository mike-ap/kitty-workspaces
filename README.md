# Kitty Workspaces

Kitty Workspaces is a no-UI [Kitty](https://sw.kovidgoyal.net/kitty/) kitten that collects and provides coding agent and
git worktree/branch state to Kitty tab names. Use it with
[Kitty Workspace Picker](https://github.com/mike-ap/kitty-workspace-picker)
for an `fzf` picker for Kitty Workspaces.

<!-- markdownlint-disable MD034 -->

https://github.com/user-attachments/assets/a824eb3d-98f7-48c0-820f-cb8d9465bad8

<!-- markdownlint-enable MD034 -->

Built for personal use, for a workflow based on multiple simple workspaces:

- Kitty Tab (workspace)
  - Agent session (vsplit)
  - Editor (vsplit)
- etc.

## Installation

Requires Kitty >= 0.50.0. Tested with Git 2.56.0 on Linux; macOS untested. `fzf` is needed only for the separately installed companion picker.

```sh
curl -fsSL https://github.com/mike-ap/kitty-workspaces/releases/latest/download/bootstrap.sh | sh
```

For a specific version or Kitty configuration directory:

```sh
curl -fsSL https://github.com/mike-ap/kitty-workspaces/releases/latest/download/bootstrap.sh | sh -s -- --version 0.1.0 --config-dir /path/to/kitty
```

## Configuration

Installation creates only the `kitty_workspaces/` package and
`tab_bar.py.example` in your Kitty configuration root.

- `tab_bar.py.example`: rename to `tab_bar.py` if you have no existing hook;
  otherwise merge its startup code and `draw_title` function into your hook.
- `kitty_workspaces/kitty-workspaces.conf`: add
  `include kitty_workspaces/kitty-workspaces.conf` to `kitty.conf`. It enables workspace titles and
  visit tracking. Navigation shortcuts and other optional settings are commented;
  uncomment the ones you want.

### Cheatsheet (defaults)

If you uncomment the Kitty Workspaces settings in kitty_workspaces/kitty-workspaces.conf,
these keybinds are enabled:

```text
ctrl+shift+a         kitten kitty_workspaces/kitten.py next-agent
ctrl+shift+backspace kitten kitty_workspaces/kitten.py previous-workspace
```

Settings belong in `kitty_workspaces.toml` beside `kitty.conf`:

```toml
strip_branch_prefix = false
```

The default is `true`, hiding leading `feature/`, `fix/`, `bugfix/`, `hotfix/`,
and `chore/` from branch names. Worktree directory names are unaffected.
Missing, unreadable, or invalid settings use the default.

## Update

Rerun the stable download command or update your checkout and repeat
[installation](#installation), then restart Kitty.

## Uninstall

Remove the workspace import/startup hook from `tab_bar.py`, the workspace watcher
and shortcuts from `kitty.conf`, and any workspace-specific title settings you
added. Then run from a checkout or extracted release:

```sh
sh install.sh --uninstall
```

Or use the installer:

```sh
curl -fsSL https://github.com/mike-ap/kitty-workspaces/releases/latest/download/bootstrap.sh | sh -s -- --uninstall
```

Use `--config-dir /path/to/kitty` for a custom configuration directory. Restart
Kitty after removal.

______________________________________________________________________

## Features

### First Line

The first title line shows the repository name, falling back to the current
directory name outside Git repositories or while Git metadata is unavailable.
Git labels use the branch in the main checkout and the worktree directory name
in linked worktrees.

### Second Line

Manual Kitty tab names take precedence on the second line, followed by agent
titles and Git context. The oldest pane containing a running agent supplies the
automatic tab title, independent of focus or pane layout. When its agent exits,
the next oldest agent pane takes over.

#### Status

Status aggregates across every agent in the tab. Workspaces with detected
agents retain a status character alongside manual names. Automatic Claude
labels use the pane's descriptive terminal title. Until a useful title is
available, labels fall back to the branch or worktree name, then the project
name. Native status markers remain visible.

Claude Code 2.1.295+ and Codex CLI 0.163.0+ support the Program Status Protocol
(OSC 7501). Kitty 0.50 reads their reports; this project uses only those native
states:

| State     | Marker | Meaning reported by the program |
| --------- | ------ | ------------------------------- |
| `idle`    | ○      | Idle                            |
| `working` | ●      | Working                         |
| `done`    | ✓      | Done                            |
| `blocked` | ?      | Waiting on the user             |
| `error`   | !      | Error                           |
| `null`    | —      | No usable report                |

Workspace status uses this priority across all agents: blocked, error, done,
working, unknown, idle. No assistant response text is parsed.

No screen parsing, `claude agents` polling, hooks, API requests, session files,
or separate completion history are used. Missing reports are Unknown. Terminals
or multiplexers that prevent protocol negotiation or forwarding cannot supply
status.

#### Next agent needing attention

Bind this Kitty action to a shortcut of your choice using `map` in `kitty.conf`:

```text
kitten kitty_workspaces/kitten.py next-agent
```

The command focuses the next agent pane reporting `blocked` (`?`) or `error`
(`!`) through OSC 7501. It cycles in tab/pane order across OS windows in the
current Kitty instance, starting after the focused pane and wrapping around.
With no matching panes, focus stays unchanged. It reads the live reports when
invoked. Kitty may clear an error report when its pane receives focus.

You can also invoke it through remote control:

```sh
kitten @ kitten /path/to/kitty_workspaces/kitten.py next-agent
```

#### MRU switching

Bind the `kitten kitty_workspaces/kitten.py previous-workspace` action to a
shortcut of your choice. The shortcut returns to the most recently visited other workspace.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for bug reports, local checks, and release
preparation, and [CHANGELOG.md](CHANGELOG.md) for user-visible changes.

## License

Copyright (c) 2026 Michael Apicelli. Licensed under the [MIT License](LICENSE).
