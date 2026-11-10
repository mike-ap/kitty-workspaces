"""Pure label composition and terminal-width truncation."""

try:
    from kitty.fast_data_types import wcswidth
except ImportError:
    wcswidth = len

from .status import STATUS_MARKERS


def printable(text):
    return "".join(filter(str.isprintable, text))


def session_label(title, session):
    session_title, status = session
    project, _, fallback = title.partition("\n")
    name = session_title or fallback or project
    marker = STATUS_MARKERS.get(status, "—") + " "
    return f"{project}\n{marker}{name}"


def workspace_lines(workspace):
    """Compose the shared display policy without discarding workspace metadata."""
    if workspace.manual_name:
        marker = STATUS_MARKERS[workspace.status] + " " if workspace.sessions else ""
        return workspace.project + "\n" + marker + workspace.manual_name
    title = workspace.project
    if workspace.worktree:
        title += "\n" + workspace.worktree
    if workspace.representative_session is not None:
        session = workspace.representative_session
        return session_label(title, (session.title, workspace.status))
    return title


def render_title(title, width, multiline):
    parts = title.split("\n")[:2]
    # Reserve both rows even for manual names or temporary fallback titles.
    # Otherwise a refresh without a second line collapses the vertical tab bar.
    if multiline and len(parts) < 2:
        parts.append("")
    lines = parts if multiline else [" · ".join(parts)]
    padding = " " if width > 2 else ""
    content_width = width - 2 * len(padding)
    return "\n".join(padding + compact(line, content_width) + padding for line in lines)


def compact(text, width):
    text = printable(text)
    if wcswidth(text) <= width:
        return text
    if width <= 1:
        return "…" if width else ""
    left, right = "", ""
    for char in text:
        if wcswidth(left + char) > width // 2:
            break
        left += char
    for char in reversed(text[len(left) :]):
        if wcswidth(char + right) > width - 1 - wcswidth(left):
            break
        right = char + right
    return left + "…" + right
