"""Check real Codex OSC 7501 against a loopback model fixture."""

import json
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread

import pytest

pytestmark = pytest.mark.kitty_integration


def test_real_codex_working_done_without_observation_setup(terminal):
    codex = shutil.which("codex")
    if codex is None:
        pytest.skip("Codex is not installed")
    release = Event()

    class Fixture(BaseHTTPRequestHandler):
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if request.get("tools"):
                release.wait(20)
            item = {
                "id": "msg_fixture",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": "fixture complete",
                        "annotations": [],
                    }
                ],
            }
            response = {
                "id": "resp_fixture",
                "object": "response",
                "status": "completed",
                "output": [item],
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            }
            events = [
                {
                    "type": "response.created",
                    "response": {**response, "status": "in_progress", "output": []},
                },
                {"type": "response.output_item.added", "output_index": 0, "item": item},
                {"type": "response.output_item.done", "output_index": 0, "item": item},
                {"type": "response.completed", "response": response},
            ]
            body = "".join(
                f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    Thread(target=server.serve_forever, daemon=True).start()
    home = Path(terminal.env["CODEX_HOME"])
    home.mkdir(exist_ok=True)
    # Model requests go exclusively to the loopback fixture. These settings are
    # inside the test HOME; there are no hooks or terminal-title overrides.
    (home / "config.toml").write_text(f"""model = "fixture"
model_provider = "fixture"
check_for_update_on_startup = false
[features]
daemon_auto_start = false
[projects.{json.dumps(str(terminal.project))}]
trust_level = "trusted"
[model_providers.fixture]
name = "Local fixture"
base_url = "http://127.0.0.1:{server.server_port}/v1"
wire_api = "responses"
requires_openai_auth = false
""")
    try:
        pane = int(
            terminal.command(
                "launch",
                "--type",
                "tab",
                "--cwd",
                terminal.project,
                "env",
                "-u",
                "CODEX_THREAD_ID",
                "-u",
                "CODEX_SESSION_ID",
                "-u",
                "CODEX_TOOL_CALL_ID",
                codex,
                "Reply fixture complete.",
            ).stdout
        )

        def observed(status):
            value = json.loads(
                terminal.command(
                    "kitten", terminal.config / "kitty_workspaces/kitten.py"
                ).stdout
            )
            return next(
                (
                    s
                    for w in value["workspaces"]
                    for s in w["sessions"]
                    if s["window_id"] == pane and s["status"] == status
                ),
                None,
            )

        busy = terminal.wait_for(
            lambda: observed("working"), "real Codex working report", timeout=15
        )
        assert busy["status_character"] == "●" and busy["pid"] > 0
        release.set()
        idle = terminal.wait_for(
            lambda: observed("done"), "real Codex done report", timeout=15
        )
        assert idle["status_character"] == "✓"
        assert not (home / "app-server-control/app-server-control.sock").exists()
    finally:
        release.set()
        server.shutdown()
        server.server_close()
