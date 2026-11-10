"""Codex-specific title and tool-process conventions."""


def terminal_title(title, cwd=None):
    prefix, separator, _ = title.rpartition(" | ")
    return prefix if separator else title


def is_tool_process(environment):
    return any(
        key in environment
        for key in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_TOOL_CALL_ID")
    )
