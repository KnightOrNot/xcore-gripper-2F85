"""Streaming commands use mocked serial hardware; no gripper is opened."""

import threading
import time
import unittest
from unittest.mock import Mock, patch

from xcore_gripper_2f85 import robtiq_gripper_mdbsrtu as wire
from xcore_gripper_2f85.gripper_server import GripperController, GripperRequestHandler
from xcore_gripper_2f85.gripper_sdk import Robotiq2F85
from fake_server import FakeGripperServer, ok_status


class FollowControllerTest(unittest.TestCase):
    def setUp(self):
        self.hardware = Mock()
        self.hardware.ReadGripperStatus.return_value = (0x39, 100, 30.39)
        self.stopped = threading.Event()
        self.hardware.stop.side_effect = self.stopped.set
        with patch(
            "xcore_gripper_2f85.gripper_server.GRP.Gripper", return_value=self.hardware
        ):
            self.controller = GripperController("fake", activate_on_start=False)

    def tearDown(self):
        self.controller.close()

    def test_update_while_moving_and_heartbeat_does_not_repeat_writes(self):
        first = self.controller.set_target(10)
        self.assertTrue(first["moving"])
        self.controller.set_target(200)
        self.controller.set_target(200)
        self.assertEqual(self.hardware.grip.call_count, 2)
        self.hardware.grip.assert_called_with([200, 150, 0])
        self.assertEqual(self.hardware.ReadGripperStatus.call_count, 3)

    def test_watchdog_stops_and_latches_until_explicit_stop(self):
        self.controller.set_target(100)
        with self.controller._lock:
            self.controller._stream_deadline = time.monotonic() - 1
        self.assertTrue(self.stopped.wait(1))
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            self.controller.set_target(120)
        self.controller.stop()
        self.controller.set_target(120)
        self.hardware.grip.assert_called_with([120, 150, 0])

    def test_manual_motion_is_rejected_during_following(self):
        self.controller.set_target(100)
        with self.assertRaisesRegex(RuntimeError, "following is active"):
            self.controller.move(255)
        with self.assertRaisesRegex(RuntimeError, "following is active"):
            self.controller.activate()

    def test_serial_fault_stops_stream_and_is_reported(self):
        self.hardware.ReadGripperStatus.side_effect = IOError("serial lost")
        with self.assertRaisesRegex(IOError, "serial lost"):
            self.controller.set_target(100)
        self.assertTrue(self.stopped.is_set())
        with self.assertRaisesRegex(RuntimeError, "serial lost"):
            self.controller.set_target(200)

    def test_read_only_capability_check_has_no_motion(self):
        state = self.controller.follow_status()
        self.assertTrue(state["streaming"])
        self.hardware.grip.assert_not_called()
        self.hardware.stop.assert_not_called()

    def test_request_dispatch_exposes_streaming_and_stop(self):
        handler = object.__new__(GripperRequestHandler)
        handler.server = Mock(controller=self.controller)
        self.assertTrue(handler.dispatch({"cmd": "follow_status"})["ok"])
        result = handler.dispatch({"cmd": "set_target", "pos": 90})
        self.assertTrue(result["result"]["moving"])
        handler.dispatch({"cmd": "stop"})
        self.assertTrue(self.stopped.is_set())

    def test_invalid_watchdog_does_not_write_serial(self):
        for stale in [0, float("nan"), float("inf"), 11]:
            with self.assertRaises(ValueError):
                self.controller.set_target(100, stale_timeout=stale)
        self.hardware.grip.assert_not_called()


class StopWireTest(unittest.TestCase):
    def test_incomplete_feedback_reports_io_error_instead_of_index_error(self):
        hardware = object.__new__(wire.Gripper)
        hardware.ser = Mock()
        for method, expected in [(hardware.isavtivated, 7), (hardware.ReadGripperStatus, 11)]:
            for size in [0, 3, expected - 1]:
                with self.subTest(method=method.__name__, size=size):
                    hardware.ser.read.return_value = bytes(size)
                    with patch.object(wire.time, "sleep"):
                        with self.assertRaisesRegex(IOError, "Incomplete Modbus"):
                            method()

    def test_complete_feedback_retains_activation_and_position_results(self):
        hardware = object.__new__(wire.Gripper)
        hardware.ser = Mock()
        hardware.ser.read.return_value = bytes([9, 4, 2, 0x31, 0, 0, 0])
        with patch.object(wire.time, "sleep"):
            self.assertTrue(hardware.isavtivated())
        hardware.ser.read.return_value = bytes([9, 4, 6, 0xF9, 0, 0, 0, 100, 0, 0, 0])
        with patch.object(wire.time, "sleep"):
            self.assertEqual(hardware.ReadGripperStatus(), (0xF9, 100, 30.39))

    def test_failed_activation_closes_serial_before_propagating_error(self):
        hardware = Mock()
        hardware.isavtivated.side_effect = IOError("Incomplete Modbus activation reply")
        with patch("xcore_gripper_2f85.gripper_server.GRP.Gripper", return_value=hardware):
            with self.assertRaisesRegex(IOError, "Incomplete Modbus"):
                GripperController("fake")
        hardware.serclose.assert_called_once()

    def test_stop_clears_goto_without_reset_or_release_and_checks_ack(self):
        hardware = object.__new__(wire.Gripper)
        hardware.ser = Mock()
        hardware.ser.read.return_value = bytes(wire.CRC([9, 16, 3, 232, 0, 3]))
        with patch.object(wire.time, "sleep"):
            hardware.stop()
        packet = hardware.ser.write.call_args.args[0]
        self.assertEqual(packet[:7], bytes([9, 16, 3, 232, 0, 3, 6]))
        self.assertEqual(packet[7], 0x01)  # rACT=1, rGTO=0, rATR=0.
        self.assertEqual(packet, bytes(wire.CRC(list(packet[:-2]))))
        hardware.ser.read.return_value = b""
        with patch.object(wire.time, "sleep"):
            with self.assertRaisesRegex(IOError, "acknowledgement"):
                hardware.stop()


class StreamingSdkTest(unittest.TestCase):
    def test_streaming_sdk_uses_new_commands_and_calibrated_range(self):
        with FakeGripperServer(lambda r: ok_status(r.get("pos", 0))) as server:
            sdk = Robotiq2F85("127.0.0.1", port=server.port)
            sdk.follow_status()
            sdk.set_target_closure(0.5, open_pos=2, closed_pos=230)
            sdk.stop()
            self.assertEqual(
                [r["cmd"] for r in server.requests],
                ["follow_status", "set_target", "stop"],
            )
            self.assertEqual(server.requests[1]["pos"], 116)


if __name__ == "__main__":
    unittest.main()
