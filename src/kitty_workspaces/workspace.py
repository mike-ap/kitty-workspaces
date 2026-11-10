"""Workspace identity and agent panes with native Kitty program status."""

from dataclasses import dataclass, field, replace

from . import agents, runtime
from .status import STATES, aggregate, reported_status


@dataclass(frozen=True)
class Session:
    agent: str
    window_id: int
    pid: int
    title: str | None
    status: str | None
    cwd: str | None = None


@dataclass(frozen=True)
class Workspace:
    id: int | None = None
    manual_name: str = ""
    project: str = ""
    worktree: str = ""
    representative_session: Session | None = None
    cwd: str | None = None
    repository_root: str | None = None
    worktree_root: str | None = None
    branch: str | None = None
    sessions: list[Session] = field(default_factory=list)

    @property
    def status(self):
        return aggregate(self.sessions)

    @property
    def session_counts(self):
        return {
            "total": len(self.sessions),
            **{
                state: sum(s.status == state for s in self.sessions) for state in STATES
            },
            "unknown": sum(s.status is None for s in self.sessions),
        }


def process_session(window, process):
    adapter = agents.for_id(process.get("agent"))
    if adapter is None:
        return None
    cwd = process.get("cwd")
    title = adapter.normalize_title(getattr(window, "title", ""), cwd)
    return Session(
        adapter.id,
        window.id,
        process["pid"],
        title,
        reported_status(window, adapter.id),
        cwd,
    )


def sessions(tab):
    windows = sorted(tab, key=lambda window: window.id)
    result = []
    for window in windows:
        detected = [
            session
            for process in runtime.pane_observation(window).get("processes", [])
            if (session := process_session(window, process)) is not None
        ]
        # OSC records identify apps, not PIDs. Never attribute the same app's
        # reports to multiple foreground processes in a pane.
        result.extend(
            replace(session, status=None)
            if sum(other.agent == session.agent for other in detected) > 1
            else session
            for session in detected
        )
    return result


def representative(detected):
    return next(iter(detected), None)


def resolve(tab, fallback_title, workspace_id=None):
    window = min(tab, key=lambda window: window.id, default=None)
    pane = runtime.pane_observation(window) if window else {}
    project, _, worktree = (pane.get("label") or fallback_title).partition("\n")
    detected = sessions(tab)
    return Workspace(
        id=workspace_id,
        manual_name=tab.name,
        project=project,
        worktree=worktree,
        representative_session=representative(detected),
        cwd=pane.get("cwd"),
        repository_root=pane.get("repository_root"),
        worktree_root=pane.get("worktree_root"),
        branch=pane.get("branch"),
        sessions=detected,
    )
