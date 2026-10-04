"""Shared fakes for the gripper test suite (stdlib only, no hardware needed)."""

from __future__ import annotations

import json
import socketserver
import threading
from typing import Any, Callable, Dict, List


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        line = self.rfile.readline(4096)
        if not line:
            return
        try:
            request = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            self.wfile.write(b'{"ok": false, "error": "bad request"}\n')
            return
        self.server.requests.append(request)  # type: ignore[attr-defined]
        response = self.server.responder(request)  # type: ignore[attr-defined]
        if isinstance(response, str):
            payload = response
        else:
            payload = json.dumps(response)
        self.wfile.write((payload + "\n").encode("utf-8"))


class FakeGripperServer(socketserver.ThreadingTCPServer):
    """Tiny stand-in for ``gripper_server.py`` speaking the JSON line protocol."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, responder: Callable[[Dict[str, Any]], Any]) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.responder = responder
        self.requests: List[Dict[str, Any]] = []
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    def __enter__(self) -> "FakeGripperServer":
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.shutdown()
        self.server_close()


def ok_status(position_raw: int = 100, status_code: int = 249) -> Dict[str, Any]:
    return {
        "ok": True,
        "result": {
            "status_code": status_code,
            "position_raw": position_raw,
            "position_mm": round(50.0 - (50.0 / 255.0) * position_raw, 2),
            "moving": status_code == 0x39,
        },
    }
