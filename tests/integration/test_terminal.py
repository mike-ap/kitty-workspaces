import pytest

pytestmark = pytest.mark.kitty_integration


def test_claude_terminal_title_overrides_default_session_name(terminal):
    import json

    tab_id, pane_id = terminal.launch_agent("CI timing", session_name="demo-90")
    terminal.wait_label(tab_id, ["demo", "○ CI timing"])
    endpoint = terminal.config / "kitty_workspaces/kitten.py"
    snapshot = json.loads(terminal.command("kitten", endpoint, "state").stdout)
    item = next(item for item in snapshot["workspaces"] if item["id"] == tab_id)
    assert item["representative_session"]["title"] == "CI timing"
    assert item["name"] == "demo\n○ CI timing"

    terminal.command("set-tab-title", "--match", f"id:{tab_id}", "My workspace")
    terminal.wait_label(tab_id, ["demo", "○ My workspace"])
    terminal.command("set-window-title", "--match", f"id:{pane_id}", "✳ Claude Code")
    terminal.command("set-tab-title", "--match", f"id:{tab_id}", "")
    terminal.wait_label(tab_id, ["demo", "○ main"])


@pytest.mark.parametrize("edge", ["top", "bottom", "left", "right"])
def test_labels_render_on_each_edge_with_symlinked_config(terminal, edge):
    terminal.command("load-config", "--override", f"tab_bar_edge={edge}")
    tab_id = terminal.snapshot()["active_tab"]
    expected = ["demo", "○ Alpha"] if edge in ("left", "right") else ["demo · ○ Alpha"]
    terminal.wait_label(tab_id, expected)
    assert (terminal.config / "tab_bar.py").is_symlink()


def test_line_limit_and_config_reload(terminal):
    tab_id = terminal.snapshot()["active_tab"]
    terminal.wait_label(tab_id, ["demo", "○ Alpha"])
    terminal.command("load-config", "--override", "tab_title_max_lines=1")
    terminal.wait_label(tab_id, ["demo · ○ Alpha"])
    terminal.command("load-config", "--override", "tab_title_max_lines=2")
    terminal.wait_label(tab_id, ["demo", "○ Alpha"])


def test_oldest_agent_title_is_stable_across_focus_and_manual_name(terminal):
    alpha = terminal.state()[0]["tabs"][0]["windows"][0]["id"]
    tab_id, beta = terminal.launch_agent("Beta", "working", kind="window")
    terminal.command("focus-window", "--match", f"id:{alpha}")
    terminal.wait_label(tab_id, ["demo", "● Alpha"])
    terminal.command("focus-window", "--match", f"id:{beta}")
    terminal.wait_label(tab_id, ["demo", "● Alpha"])

    terminal.command("focus-window", "--match", f"id:{alpha}")
    terminal.wait_label(tab_id, ["demo", "● Alpha"])
    terminal.command("set-tab-title", "--match", f"id:{tab_id}", "My custom tab")
    terminal.wait_label(tab_id, ["demo", "● My custom tab"])
    terminal.command("focus-window", "--match", f"id:{beta}")
    terminal.wait_label(tab_id, ["demo", "● My custom tab"])
    terminal.command("set-tab-title", "--match", f"id:{tab_id}", "")
    terminal.wait_label(tab_id, ["demo", "● Alpha"])


def test_published_metadata_uses_workspace_identity_and_naming(terminal):
    import json

    workspace_id = terminal.snapshot()["active_tab"]
    owner_id = terminal.state()[0]["tabs"][0]["windows"][0]["id"]
    _, pane_id = terminal.launch_agent("Beta", "working", kind="window")
    endpoint = terminal.config / "kitty_workspaces/kitten.py"

    def published():
        snapshot = json.loads(terminal.command("kitten", endpoint).stdout)
        assert snapshot["version"] == 1
        return next(
            item for item in snapshot["workspaces"] if item["id"] == workspace_id
        )

    item = terminal.wait_for(
        lambda: (
            item
            if (item := published())["representative_session"]
            and item["representative_session"]["window_id"] == owner_id
            and item["representative_session"]["title"] == "Alpha"
            and item["status"] == "working"
            and item["branch"] == "main"
            else None
        ),
        "process discovery and the independent Git observation",
    )
    assert item["name"] == "demo\n● Alpha"
    assert item["status"] == "working"
    assert item["project"] == "demo"
    assert item["worktree"] == "main"
    assert item["representative_session"]["title"] == "Alpha"
    assert item["representative_session"]["status"] == "idle"
    assert (
        item["representative_session"]["window_id"] == owner_id
        and item["representative_session"]["title"] == "Alpha"
        and item["status"] == "working"
    )
    assert pane_id in item["window_ids"]
    assert len(item["window_ids"]) == 2
    terminal.command("set-tab-title", "--match", f"id:{workspace_id}", "My workspace")
    renamed = published()
    assert renamed["name"] == "demo\n● My workspace"
    for field in (
        "project",
        "worktree",
        "cwd",
        "repository_root",
        "worktree_root",
        "branch",
        "sessions",
        "representative_session",
    ):
        assert renamed[field] == item[field]
    assert renamed["branch"] == "main"
    assert renamed["active_window_id"] == pane_id
    assert renamed["is_active"] is True


def test_codex_native_status_is_pane_local_with_duplicate_titles(terminal):
    import json
    import sys
    from pathlib import Path

    fixture = Path(__file__).with_name("codex_agent.py")
    panes = [
        int(
            terminal.command(
                "launch",
                "--type",
                "tab",
                "--cwd",
                terminal.project,
                sys.executable,
                fixture,
                status,
            ).stdout
        )
        for status in ("working", "idle")
    ]
    endpoint = terminal.config / "kitty_workspaces/kitten.py"

    def observed():
        value = json.loads(terminal.command("kitten", endpoint).stdout)
        return {
            s["window_id"]: s
            for w in value["workspaces"]
            for s in w["sessions"]
            if s["window_id"] in panes
        }

    terminal.wait_for(
        lambda: (
            len(observed()) == 2
            and [observed()[pane]["status"] for pane in panes] == ["working", "idle"]
        ),
        "duplicate-title Codex panes to report independent activity",
    )
    for pane, marker in zip(panes, ("●", "○"), strict=True):
        row = observed()[pane]
        assert row["pid"] > 0
        assert set(row) == {
            "agent",
            "window_id",
            "pid",
            "title",
            "status",
            "cwd",
            "status_character",
        }
        terminal.wait_label(
            terminal.tab_for_window(pane), ["demo", marker + " Duplicate"]
        )
    terminal.command("send-text", "--match", f"id:{panes[0]}", "idle\n")
    terminal.wait_label(terminal.tab_for_window(panes[0]), ["demo", "○ Duplicate"])
    assert observed()[panes[0]]["status"] == "idle"


def test_mru_watcher_and_previous_workspace(terminal):
    import json

    endpoint = terminal.config / "kitty_workspaces/kitten.py"
    alpha = terminal.state()[0]["tabs"][0]["windows"][0]["id"]
    _, beta = terminal.launch_agent("Beta", kind="tab")
    _, gamma = terminal.launch_agent("Gamma", kind="tab")
    # Visit using native Kitty navigation, without asking the metadata endpoint
    # to sample between visits. The watcher must see these transitions itself.
    for pane in (alpha, beta, gamma):
        terminal.command("focus-window", "--match", f"id:{pane}")
    for expected in (beta, gamma, beta):
        result = json.loads(
            terminal.command("kitten", endpoint, "previous-workspace").stdout
        )
        assert result["window_id"] == expected
    metadata = json.loads(terminal.command("kitten", endpoint, "state").stdout)
    entries = metadata["workspaces"]
    visits = {item["active_window_id"]: item["last_visited_order"] for item in entries}
    assert visits[beta] > visits[gamma] > visits[alpha]


def test_mru_preserves_panes_prunes_tabs_and_crosses_os_windows(terminal):
    import json

    endpoint = terminal.config / "kitty_workspaces/kitten.py"

    def previous():
        return json.loads(
            terminal.command("kitten", endpoint, "previous-workspace").stdout
        )

    def visits():
        data = json.loads(terminal.command("kitten", endpoint, "state").stdout)
        return {item["id"]: item["last_visited_order"] for item in data["workspaces"]}

    alpha_tab = terminal.snapshot()["active_tab"]
    alpha = terminal.state()[0]["tabs"][0]["windows"][0]["id"]
    _, second_pane = terminal.launch_agent("Second pane", kind="window")
    initial = visits()[alpha_tab]
    terminal.command("focus-window", "--match", f"id:{alpha}")
    terminal.command("focus-window", "--match", f"id:{second_pane}")
    assert visits()[alpha_tab] == initial

    beta_tab, beta = terminal.launch_agent("Beta", kind="tab")
    assert previous()["window_id"] == second_pane
    assert previous()["window_id"] == beta

    gamma_tab, gamma = terminal.launch_agent("Gamma", kind="os-window")
    assert previous()["window_id"] == beta
    assert previous()["window_id"] == gamma
    terminal.command("close-tab", "--match", f"id:{beta_tab}")
    assert previous()["window_id"] == second_pane
    assert beta_tab not in visits()
    terminal.command("close-tab", "--match", f"id:{gamma_tab}")
    assert previous() is None


@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_native_status_changes_clear_and_attention_navigation(terminal, agent):
    import json
    import sys
    from pathlib import Path

    if agent == "claude":
        tab_id, pane = terminal.launch_agent("Native", "working")
        title = "Native"
    else:
        pane = int(
            terminal.command(
                "launch",
                "--type",
                "tab",
                "--cwd",
                terminal.project,
                sys.executable,
                Path(__file__).with_name("codex_agent.py"),
                "working",
            ).stdout
        )
        tab_id = terminal.tab_for_window(pane)
        title = "Duplicate"
    endpoint = terminal.config / "kitty_workspaces/kitten.py"
    alpha = terminal.state()[0]["tabs"][0]["windows"][0]["id"]
    terminal.command("focus-window", "--match", f"id:{alpha}")

    def status():
        value = json.loads(terminal.command("kitten", endpoint, "state").stdout)
        return next(
            (
                s
                for w in value["workspaces"]
                for s in w["sessions"]
                if s["window_id"] == pane
            ),
            {},
        ).get("status")

    for state, marker in [
        ("working", "●"),
        ("blocked", "?"),
        ("error", "!"),
        ("done", "✓"),
        ("idle", "○"),
        ("clear", "—"),
    ]:
        terminal.command("send-text", "--match", f"id:{pane}", state + "\n")
        terminal.wait_label(tab_id, ["demo", marker + " " + title])
        assert status() == (None if state == "clear" else state)
    assert json.loads(terminal.command("kitten", endpoint, "next-agent").stdout) is None
    terminal.command("send-text", "--match", f"id:{pane}", "blocked\n")
    terminal.wait_for(lambda: status() == "blocked", "native blocked report")
    assert json.loads(terminal.command("kitten", endpoint, "next-agent").stdout) == {
        "window_id": pane,
        "tab_id": tab_id,
    }
    # Kitty owns the lifetime of done/error records and clears them on focus.
    terminal.command("focus-window", "--match", f"id:{alpha}")
    terminal.command("send-text", "--match", f"id:{pane}", "done\n")
    terminal.wait_for(lambda: status() == "done", "native completion")
    terminal.command("focus-window", "--match", f"id:{pane}")
    terminal.wait_for(lambda: status() is None, "Kitty to clear seen completion")


def test_wrapper_aware_process_reporting_matches_kitty_ls(terminal):
    import json
    import sys
    from pathlib import Path

    pane_id = int(
        terminal.command(
            "launch",
            "--type",
            "tab",
            "--hold",
            "--cwd",
            terminal.project,
            sys.executable,
            Path(__file__).with_name("agent.py"),
            "Held",
            "working",
        ).stdout
    )
    endpoint = terminal.config / "kitty_workspaces/kitten.py"

    def observed():
        data = json.loads(terminal.command("kitten", endpoint, "state").stdout)
        return next(
            (
                s
                for w in data["workspaces"]
                for s in w["sessions"]
                if s["window_id"] == pane_id
            ),
            None,
        )

    session = terminal.wait_for(observed, "agent behind Kitty's hold wrapper")
    reported = next(
        p
        for osw in terminal.state()
        for tab in osw["tabs"]
        for p in tab["windows"]
        if p["id"] == pane_id
    )
    assert session["pid"] == reported["pid"]
    assert session["cwd"] == reported["cwd"] == str(terminal.project)
    assert session["status"] == "working"


def test_idle_kitty_consumes_collector_updates_without_control_polling(terminal):
    import subprocess
    from time import sleep

    tab_id = terminal.snapshot()["active_tab"]
    pane_id = terminal.snapshot()["active_window"]
    # Hide the agent's descriptive title so the branch is visible on row two.
    terminal.command("set-window-title", "--match", f"id:{pane_id}", "Claude Code")
    terminal.wait_label(tab_id, ["demo", "○ main"])
    subprocess.run(
        [
            "git",
            "-C",
            str(terminal.project),
            "symbolic-ref",
            "HEAD",
            "refs/heads/idle-refresh",
        ],
        check=True,
    )
    # Polling Kitty itself can give Python threads scheduling opportunities and
    # conceal starvation in its native idle loop. Leave it completely alone.
    # Git refreshes every ten seconds, separately from the two-second process poll.
    sleep(15)
    assert terminal.snapshot()["labels"][str(tab_id)] == ["demo", "○ idle-refresh"]
