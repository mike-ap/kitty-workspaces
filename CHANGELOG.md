# Changelog

User-visible changes are recorded here. Entries remain under Unreleased until
a release is tagged.

## Unreleased

## 0.1.5 - 2026-11-20

- Refresh tab names more quickly while keeping process and Git discovery in the
  background and avoiding unchanged input snapshot writes.
- Verified on Linux with Kitty 0.50.0, Kitty Python 3.14.10, and development
  Python 3.12.15: all 16 isolated graphical checks passed, including the real
  Codex CLI 0.169.0 test using a local model fixture.

## 0.1.4 - 2026-11-15

- Add a direct link to Kitty in the README introduction.

## 0.1.3 - 2026-11-11

- Focus the README cheatsheet on next-agent and previous-workspace shortcuts.
- Separate optional Kitty Workspaces navigation bindings from recommended Kitty
  settings and remove outdated shortcut placeholder instructions.

## 0.1.2 - 2026-11-11

- Simplify the installation and configuration guide and add an optional shortcut
  cheatsheet.
- Provide concrete optional shortcuts for next-agent navigation
  (`ctrl+shift+a`) and previous-workspace switching (`ctrl+shift+backspace`),
  and use `ctrl+shift+n` for the optional tab-title shortcut.

## 0.1.1 - 2026-11-11

- Simplify publishing with `just release VERSION`: update the project version and
  lockfile, move Unreleased notes into a dated changelog section, and commit the
  prepared release before tagging and pushing it.
- Keep release checks and source archive verification ahead of the release commit
  and tag. Failed checks leave prepared files available for inspection without
  publishing a release.
- Document the automated release workflow and recovery steps for failed checks
  or pushes.

## 0.1.0 - 2026-11-11

- initial release
