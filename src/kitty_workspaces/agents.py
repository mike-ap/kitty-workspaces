"""Built-in agent adapters, shared by the worker and Kitty UI process.

Callbacks must be pure: the collector owns process/environment reads, while
Kitty owns native status reports. Registration order resolves overlapping matches.
"""

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from . import claude, codex


def terminal_title(title: str, cwd: str | None) -> str | None:
    return title.strip() or None


@dataclass(frozen=True)
class AgentAdapter:
    id: str
    executables: tuple[str, ...]
    status_app: str | None = None
    normalize_title: Callable[[str, str | None], str | None] = terminal_title
    matches_command: Callable[[list[str]], bool] | None = None
    exclude_environment: Callable[[Mapping[str, str]], bool] | None = None

    def matches(self, command: list[str]) -> bool:
        if self.matches_command is not None:
            return self.matches_command(command)
        return bool(command) and os.path.basename(command[0]) in self.executables


ADAPTERS = (
    AgentAdapter("claude", ("claude",), "claude-code", claude.terminal_title),
    AgentAdapter(
        "codex",
        ("codex",),
        "codex",
        codex.terminal_title,
        exclude_environment=codex.is_tool_process,
    ),
)


def for_command(command: list[str]) -> AgentAdapter | None:
    return next((adapter for adapter in ADAPTERS if adapter.matches(command)), None)


def for_id(agent: str) -> AgentAdapter | None:
    return next((adapter for adapter in ADAPTERS if adapter.id == agent), None)
