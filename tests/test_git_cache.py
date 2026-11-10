import json
from threading import Event
from time import monotonic, sleep

from kitty_workspaces import collector, git_cache


def wait_for(predicate):
    deadline = monotonic() + 2
    while not predicate():
        assert monotonic() < deadline
        sleep(0.005)


def test_stalled_git_does_not_block_process_publication_or_shutdown(
    monkeypatch, tmp_path
):
    entered, release = Event(), Event()

    def label(*args):
        entered.set()
        assert release.wait(5)
        return "demo\nmain"

    monkeypatch.setattr(git_cache.worktrees, "label", label)
    monkeypatch.setattr(
        git_cache.worktrees, "context", lambda *args: ("/demo", "/demo", "main")
    )
    monkeypatch.setattr(collector, "parent_alive", lambda pid: True)
    generation = 0

    def collect(path):
        nonlocal generation
        generation += 1
        return [
            {
                "id": 1,
                "cwd": "/demo",
                "processes": [{"pid": generation, "agent": "codex"}],
            }
        ]

    monkeypatch.setattr(collector, "collect_panes", collect)
    cache = git_cache.GitCache()
    output = tmp_path / "snapshot.json"
    try:
        collector.poll(output, tmp_path / "input", 42, 2, True, lambda: False, cache)
        assert entered.wait(2)
        for _ in range(3):
            collector.poll(
                output, tmp_path / "input", 42, 2, True, lambda: False, cache
            )
        snapshot = json.loads(output.read_text())
        assert snapshot["panes"][0]["processes"][0]["pid"] == 4
        assert snapshot["error"] is None
        cache.close()
        assert cache.thread.is_alive()  # Shutdown did not wait for the blocked lookup.
    finally:
        release.set()
        cache.close()
        cache.thread.join(2)
    assert not cache.thread.is_alive()


def test_git_refresh_expiry_directory_changes_and_failure(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(git_cache, "monotonic", lambda: now[0])
    calls = []

    def label(cwd, bucket):
        calls.append(cwd)
        if cwd == "/broken":
            raise OSError("unavailable storage")
        return "demo\nmain"

    monkeypatch.setattr(git_cache.worktrees, "label", label)
    monkeypatch.setattr(
        git_cache.worktrees, "context", lambda *args: ("/demo", "/demo", "main")
    )
    cache = git_cache.GitCache()
    try:
        cache.enrich([{"cwd": "/demo"}, {"cwd": "/demo"}])
        wait_for(lambda: "/demo" in cache.results)
        pane = {"cwd": "/demo"}
        cache.enrich([pane])
        assert pane["branch"] == "main"
        assert calls == ["/demo"]
        now[0] = 111
        cache.enrich([pane])
        wait_for(lambda: len(calls) == 2 and cache.results["/demo"][0] == 111)
        # Stop the observer to simulate an indefinitely blocked next lookup.
        cache.close()
        cache.thread.join(2)
        now[0] = 142
        fresh_pane = {"cwd": "/demo", "label": "demo", "branch": None}
        cache.enrich([fresh_pane])
        assert fresh_pane["branch"] is None
        assert fresh_pane["label"] == "demo"
        cache.enrich([{"cwd": "/other"}])
        assert cache.results == {}
    finally:
        cache.close()
        cache.thread.join(2)

    cache = git_cache.GitCache()
    try:
        cache.enrich([{"cwd": "/broken"}, {"cwd": "/demo"}])
        wait_for(lambda: "/demo" in cache.results)
        assert cache.results["/broken"][1] == {}
        assert cache.results["/demo"][1]["branch"] == "main"
    finally:
        cache.close()
        cache.thread.join(2)
