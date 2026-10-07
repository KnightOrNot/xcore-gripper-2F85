"""Unit tests for the Robotiq 2F-85 SDK helpers and transport."""

from __future__ import annotations

import socket
import unittest

from xcore_gripper_2f85.gripper_client import GripperConnectionError, send_command
from xcore_gripper_2f85.gripper_sdk import (
    MAX_POSITION,
    GripperSDKError,
    Robotiq2F85,
    closure_to_pos,
    pos_to_closure,
    pos_to_width_mm,
)

from fake_server import FakeGripperServer, ok_status


class PositionMappingTest(unittest.TestCase):
    def test_closure_endpoints(self) -> None:
        self.assertEqual(closure_to_pos(0.0), 0)
        self.assertEqual(closure_to_pos(1.0), MAX_POSITION)

    def test_closure_is_clamped(self) -> None:
        self.assertEqual(closure_to_pos(-5.0), 0)
        self.assertEqual(closure_to_pos(42.0), MAX_POSITION)

    def test_closure_round_trip_is_close(self) -> None:
        for raw in (0, 1, 100, 254, 255):
            self.assertEqual(closure_to_pos(pos_to_closure(raw)), raw)

    def test_closure_rejects_nan(self) -> None:
        with self.assertRaises(ValueError):
            closure_to_pos(float("nan"))

    def test_pos_to_closure_rejects_junk(self) -> None:
        with self.assertRaises(ValueError):
            pos_to_closure(None)

    def test_closure_remap_uses_mechanical_range(self) -> None:
        self.assertEqual(closure_to_pos(0.0, open_pos=2, closed_pos=230), 2)
        self.assertEqual(closure_to_pos(1.0, open_pos=2, closed_pos=230), 230)
        self.assertEqual(closure_to_pos(0.5, open_pos=2, closed_pos=230), 116)

    def test_closure_remap_validates_range(self) -> None:
        with self.assertRaises(ValueError):
            closure_to_pos(0.5, open_pos=-1)
        with self.assertRaises(ValueError):
            closure_to_pos(0.5, closed_pos=300)

    def test_width_matches_server_formula(self) -> None:
        self.assertEqual(pos_to_width_mm(0), 50.0)
        self.assertEqual(pos_to_width_mm(255), 0.0)
        self.assertEqual(pos_to_width_mm(100), 30.39)


class SdkTest(unittest.TestCase):
    def test_status_and_normalized_read(self) -> None:
        with FakeGripperServer(lambda request: ok_status(100)) as server:
            gripper = Robotiq2F85("127.0.0.1", port=server.port)
            result = gripper.status()
            self.assertEqual(result["position_raw"], 100)
            self.assertAlmostEqual(gripper.closure(), 100 / 255)

    def test_move_closure_translates_to_raw_position(self) -> None:
        with FakeGripperServer(lambda request: ok_status(request.get("pos", 0))) as server:
            gripper = Robotiq2F85("127.0.0.1", port=server.port)
            gripper.move_closure(1.0)
            gripper.move_openness(1.0)
            self.assertEqual(
                [request["pos"] for request in server.requests], [255, 0]
            )

    def test_server_error_becomes_sdk_error(self) -> None:
        with FakeGripperServer(lambda request: {"ok": False, "error": "boom"}) as server:
            gripper = Robotiq2F85("127.0.0.1", port=server.port)
            with self.assertRaises(GripperSDKError):
                gripper.status()

    def test_non_dict_result_is_rejected(self) -> None:
        with FakeGripperServer(lambda request: {"ok": True, "result": 3}) as server:
            gripper = Robotiq2F85("127.0.0.1", port=server.port)
            with self.assertRaises(GripperSDKError):
                gripper.status()

    def test_connection_refused_is_reported(self) -> None:
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        unused_port = probe.getsockname()[1]
        probe.close()
        with self.assertRaises(GripperConnectionError):
            send_command("127.0.0.1", unused_port, {"cmd": "status"}, timeout=0.5)

    def test_invalid_json_is_reported(self) -> None:
        with FakeGripperServer(lambda request: "not json") as server:
            with self.assertRaises(GripperConnectionError):
                send_command(
                    "127.0.0.1", server.port, {"cmd": "status"}, timeout=2.0
                )


if __name__ == "__main__":
    unittest.main()
