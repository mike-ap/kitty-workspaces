"""The five OSC 7501 states, without agent-specific inference."""

from . import agents

STATES = ("idle", "working", "done", "blocked", "error")
STATUS_MARKERS = {
    "idle": "○",
    "working": "●",
    "done": "✓",
    "blocked": "?",
    "error": "!",
    None: "—",
}
# Match Kitty's urgency, with missing reports ahead of idle for visibility.
PRIORITY = ("blocked", "error", "done", "working", None, "idle")


def reported_status(window, agent):
    """Use only this agent's records, including inherited subtask app names."""
    adapter = agents.for_id(agent)
    if adapter is None or adapter.status_app is None:
        return None
    reports = getattr(window, "program_status", None)
    if reports is None:
        return None
    records = [r for r in reports.as_list() if r.get("app") == adapter.status_app]
    if not records or any(r.get("state") not in STATES for r in records):
        return None
    return next(
        state for state in PRIORITY if any(r["state"] == state for r in records)
    )


def aggregate(sessions):
    statuses = {session.status for session in sessions}
    return next((state for state in PRIORITY if state in statuses), None)
