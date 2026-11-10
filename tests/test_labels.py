import pytest

from kitty_workspaces.labels import render_title, session_label


@pytest.mark.parametrize("title", ["", "Shell", "demo\nmain"])
@pytest.mark.parametrize("width", [1, 2, 20])
def test_multiline_titles_always_reserve_two_rows(title, width):
    lines = render_title(title, width, True).split("\n")
    assert len(lines) == 2
    assert all(len(line) <= width for line in lines)


@pytest.mark.parametrize(
    ("session", "expected"),
    [
        (("Task", "working"), "demo\n● Task"),
        (("Task", "idle"), "demo\n○ Task"),
        (("Task", None), "demo\n— Task"),
        ((None, "idle"), "demo\n○ branch"),
    ],
)
def test_session_label_retains_status_and_fallback_name(session, expected):
    assert session_label("demo\nbranch", session) == expected


@pytest.mark.parametrize("multiline", [False, True])
@pytest.mark.parametrize("width", [1, 2, 8, 20])
def test_rendered_title_fits_available_width(multiline, width):
    title = render_title("long-project-name\n● long-session-name", width, multiline)

    assert all(len(line) <= width for line in title.split("\n"))
    assert ("\n" in title) == multiline


def test_workspace_marker_includes_busy_nonrepresentative_agent():
    from kitty_workspaces.labels import workspace_lines
    from kitty_workspaces.workspace import Session, Workspace

    idle = Session("claude", 1, 10, "Idle task", "idle")
    busy = Session("claude", 2, 20, "Busy task", "working")
    item = Workspace(project="demo", representative_session=idle, sessions=[idle, busy])
    assert workspace_lines(item) == "demo\n● Idle task"


def test_manual_name_retains_attention_from_another_pane():
    from kitty_workspaces.labels import workspace_lines
    from kitty_workspaces.workspace import Session, Workspace

    session = Session("claude", 2, 20, "Question", "blocked")
    item = Workspace(
        project="demo", worktree="main", manual_name="My workspace", sessions=[session]
    )
    assert workspace_lines(item) == "demo\n? My workspace"
    assert workspace_lines(Workspace(manual_name="Shell")) == "\nShell"


def test_done_is_a_native_state_not_a_separate_unread_marker():
    from kitty_workspaces.labels import workspace_lines
    from kitty_workspaces.workspace import Session, Workspace

    session = Session("codex", 1, 10, "Task", "done")
    assert (
        workspace_lines(
            Workspace(
                project="demo", sessions=[session], representative_session=session
            )
        )
        == "demo\n✓ Task"
    )
