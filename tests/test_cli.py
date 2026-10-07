"""End-to-end tests for the ``gripper`` command line interface."""

from __future__ import annotations

import contextlib
import io
import json
import unittest

from xcore_gripper_2f85 import cli

from fake_server import FakeGripperServer, ok_status


def run_cli(argv):
    """Run the CLI in-process, returning (exit_code, stdout, stderr)."""

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(argv)
        except SystemExit as exc:  # argparse errors and SystemExit messages
            if isinstance(exc.code, str):
                err.write(exc.code + "\n")
                code = 1
            else:
                code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def test_status_plain_output(self) -> None:
        with FakeGripperServer(lambda request: ok_status(100)) as server:
            code, out, _ = run_cli(
                ["status", "--host", "127.0.0.1", "--port", str(server.port)]
            )
        self.assertEqual(code, 0)
        self.assertIn("position_raw=100", out)
        self.assertIn("closure=0.392", out)

    def test_status_json_output(self) -> None:
        with FakeGripperServer(lambda request: ok_status(2)) as server:
            code, out, _ = run_cli(
                ["status", "--json", "--host", "127.0.0.1", "--port", str(server.port)]
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["position_raw"], 2)

    def test_legacy_positional_host_form(self) -> None:
        with FakeGripperServer(lambda request: ok_status(7)) as server:
            code, out, _ = run_cli(
                ["127.0.0.1", "status", "--port", str(server.port)]
            )
        self.assertEqual(code, 0)
        self.assertIn("position_raw=7", out)

    def test_open_and_close_commands(self) -> None:
        with FakeGripperServer(lambda request: ok_status(0)) as server:
            run_cli(["open", "--speed", "150", "--host", "127.0.0.1", "--port", str(server.port)])
            run_cli(["close", "--force", "80", "--host", "127.0.0.1", "--port", str(server.port)])
            run_cli(["activate", "--host", "127.0.0.1", "--port", str(server.port)])
        self.assertEqual(
            [request["cmd"] for request in server.requests],
            ["open", "close", "activate"],
        )
        self.assertEqual(server.requests[0]["speed"], 150)
        self.assertEqual(server.requests[1]["force"], 80)

    def test_move_targets(self) -> None:
        with FakeGripperServer(lambda request: ok_status(request.get("pos", 0))) as server:
            run_cli(["move", "--pos", "100", "--host", "127.0.0.1", "--port", str(server.port)])
            run_cli(["move", "--closure", "0.5", "--host", "127.0.0.1", "--port", str(server.port)])
            run_cli(["move", "--openness", "1", "--host", "127.0.0.1", "--port", str(server.port)])
        self.assertEqual([request["pos"] for request in server.requests], [100, 128, 0])

    def test_move_with_calibrated_mechanical_range(self) -> None:
        with FakeGripperServer(lambda request: ok_status(request.get("pos", 0))) as server:
            run_cli(
                [
                    "move",
                    "--closure",
                    "1",
                    "--open-pos",
                    "2",
                    "--closed-pos",
                    "230",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(server.port),
                ]
            )
            run_cli(
                [
                    "move",
                    "--openness",
                    "1",
                    "--open-pos",
                    "2",
                    "--closed-pos",
                    "230",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(server.port),
                ]
            )
        self.assertEqual([request["pos"] for request in server.requests], [230, 2])

    def test_move_requires_a_target(self) -> None:
        code, _, err = run_cli(["move", "--host", "127.0.0.1"])
        self.assertEqual(code, 2)
        self.assertIn("required", err)

    def test_move_rejects_out_of_range_pos(self) -> None:
        code, _, err = run_cli(["move", "--pos", "999", "--host", "127.0.0.1"])
        self.assertEqual(code, 1)
        self.assertIn("0..255", err)

    def test_server_error_returns_failure(self) -> None:
        with FakeGripperServer(lambda request: {"ok": False, "error": "boom"}) as server:
            code, _, err = run_cli(
                ["status", "--host", "127.0.0.1", "--port", str(server.port)]
            )
        self.assertEqual(code, 1)
        self.assertIn("boom", err)

    def test_watch_jsonl_stream(self) -> None:
        with FakeGripperServer(lambda request: ok_status(50)) as server:
            code, out, _ = run_cli(
                [
                    "watch",
                    "--samples",
                    "3",
                    "--interval",
                    "0.01",
                    "--format",
                    "jsonl",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(server.port),
                ]
            )
        lines = [line for line in out.splitlines() if line.strip()]
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 3)
        sample = json.loads(lines[0])
        self.assertEqual(sample["position_raw"], 50)
        self.assertAlmostEqual(sample["closure"], 50 / 255)

    def test_watch_csv_stream(self) -> None:
        with FakeGripperServer(lambda request: ok_status(0)) as server:
            code, out, _ = run_cli(
                [
                    "watch",
                    "--samples",
                    "1",
                    "--interval",
                    "0.01",
                    "--format",
                    "csv",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(server.port),
                ]
            )
        lines = [line for line in out.splitlines() if line.strip()]
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 2)  # header + one sample
        self.assertEqual(lines[0].split(",")[0], "wall_time")

    def test_watch_duration_bound(self) -> None:
        with FakeGripperServer(lambda request: ok_status(0)) as server:
            code, out, _ = run_cli(
                [
                    "watch",
                    "--duration",
                    "0.05",
                    "--interval",
                    "0.01",
                    "--format",
                    "jsonl",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(server.port),
                ]
            )
        self.assertEqual(code, 0)
        self.assertGreaterEqual(len([line for line in out.splitlines() if line.strip()]), 1)


if __name__ == "__main__":
    unittest.main()
