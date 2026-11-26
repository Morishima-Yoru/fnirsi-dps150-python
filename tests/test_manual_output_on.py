"""Offline tests for the manual output-enable safety gate."""

import os
import unittest
from unittest.mock import call, patch

import manual_output_on
from fnirsi_dps150 import DeviceStatus


class ManualOutputOnTests(unittest.TestCase):
    def test_float32_test_setpoints_never_round_above_operator_ceiling(self) -> None:
        current_setpoint = manual_output_on._float32_at_or_below(0.1)

        self.assertLessEqual(current_setpoint, 0.1)
        self.assertGreater(current_setpoint, 0.0)
        self.assertEqual(manual_output_on._float32_at_or_below(1.0), 1.0)

    def test_opt_in_is_required_before_prompt_or_connection(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("builtins.input") as prompt,
            patch("manual_output_on.DPS150") as device_factory,
        ):
            with self.assertRaises(SystemExit):
                manual_output_on.main()

        prompt.assert_not_called()
        device_factory.assert_not_called()

    def test_declined_no_load_confirmation_never_opens_device(self) -> None:
        with (
            patch.dict(os.environ, {"DPS150_ALLOW_OUTPUT_ON_TEST": "1"}, clear=True),
            patch("builtins.input", return_value="no"),
            patch("manual_output_on.DPS150") as device_factory,
        ):
            with self.assertRaises(SystemExit):
                manual_output_on.main()

        device_factory.assert_not_called()

    def test_output_uses_operator_ceilings_and_restores_setpoints(self) -> None:
        current_ceiling = manual_output_on._float32_at_or_below(0.1)
        initial = DeviceStatus(12.0, 5.0, False, 19.7, 5.1)
        capped = DeviceStatus(1.0, current_ceiling, False, 19.7, 5.1)
        enabled = DeviceStatus(1.0, current_ceiling, True, 19.7, 5.1)
        output_off = DeviceStatus(1.0, current_ceiling, False, 19.7, 5.1)
        restored = DeviceStatus(12.0, 5.0, False, 19.7, 5.1)
        with (
            patch.dict(
                os.environ,
                {"DPS150_ALLOW_OUTPUT_ON_TEST": "1"},
                clear=True,
            ),
            patch(
                "builtins.input",
                side_effect=["NO LOAD CONNECTED", "1.0", "0.1"],
            ),
            patch("manual_output_on.DPS150") as device_factory,
        ):
            device = device_factory.return_value
            device.get_status.side_effect = [initial, capped, enabled, output_off, restored]
            manual_output_on.main()

        self.assertEqual(
            device.mock_calls,
            [
                call.open(),
                call.get_status(),
                call.set_voltage(1.0),
                call.set_current(current_ceiling),
                call.get_status(),
                call.set_output(True),
                call.get_status(),
                call.set_output(False),
                call.get_status(),
                call.set_voltage(12.0),
                call.set_current(5.0),
                call.get_status(),
                call.close(),
            ],
        )

    def test_operator_ceilings_must_fit_device_limits(self) -> None:
        status = DeviceStatus(12.0, 5.0, False, 0.5, 0.05)
        with (
            patch.dict(
                os.environ,
                {"DPS150_ALLOW_OUTPUT_ON_TEST": "1"},
                clear=True,
            ),
            patch(
                "builtins.input",
                side_effect=["NO LOAD CONNECTED", "1.0", "0.1"],
            ),
            patch("manual_output_on.DPS150") as device_factory,
        ):
            device = device_factory.return_value
            device.get_status.return_value = status
            with self.assertRaisesRegex(RuntimeError, "voltage ceiling"):
                manual_output_on.main()

        device.set_voltage.assert_not_called()
        device.set_current.assert_not_called()
        device.set_output.assert_not_called()
        device.close.assert_called_once_with()

    def test_already_enabled_output_is_not_changed(self) -> None:
        status = DeviceStatus(5.0, 0.5, True, 20.0, 5.0)
        with (
            patch.dict(
                os.environ,
                {"DPS150_ALLOW_OUTPUT_ON_TEST": "1"},
                clear=True,
            ),
            patch(
                "builtins.input",
                side_effect=["NO LOAD CONNECTED", "1.0", "0.1"],
            ),
            patch("manual_output_on.DPS150") as device_factory,
        ):
            device = device_factory.return_value
            device.get_status.return_value = status
            with self.assertRaisesRegex(RuntimeError, "already enabled"):
                manual_output_on.main()

        device.set_output.assert_not_called()
        device.set_voltage.assert_not_called()
        device.set_current.assert_not_called()
        device.close.assert_called_once_with()

    def test_output_is_turned_off_after_state_readback_failure(self) -> None:
        current_ceiling = manual_output_on._float32_at_or_below(0.1)
        initial = DeviceStatus(12.0, 5.0, False, 19.7, 5.1)
        capped = DeviceStatus(1.0, current_ceiling, False, 19.7, 5.1)
        output_off = DeviceStatus(1.0, current_ceiling, False, 19.7, 5.1)
        restored = DeviceStatus(12.0, 5.0, False, 19.7, 5.1)
        with (
            patch.dict(
                os.environ,
                {"DPS150_ALLOW_OUTPUT_ON_TEST": "1"},
                clear=True,
            ),
            patch(
                "builtins.input",
                side_effect=["NO LOAD CONNECTED", "1.0", "0.1"],
            ),
            patch("manual_output_on.DPS150") as device_factory,
        ):
            device = device_factory.return_value
            device.get_status.side_effect = [
                initial,
                capped,
                RuntimeError("read failed"),
                output_off,
                restored,
            ]
            with self.assertRaisesRegex(RuntimeError, "read failed"):
                manual_output_on.main()

        self.assertEqual(device.set_output.call_args_list, [call(True), call(False)])
        self.assertEqual(
            device.set_voltage.call_args_list,
            [call(1.0), call(12.0)],
        )
        self.assertEqual(
            device.set_current.call_args_list,
            [call(current_ceiling), call(5.0)],
        )
        device.close.assert_called_once_with()

    def test_original_setpoints_are_not_restored_if_output_stays_enabled(self) -> None:
        current_ceiling = manual_output_on._float32_at_or_below(0.1)
        initial = DeviceStatus(12.0, 5.0, False, 19.7, 5.1)
        capped = DeviceStatus(1.0, current_ceiling, False, 19.7, 5.1)
        enabled = DeviceStatus(1.0, current_ceiling, True, 19.7, 5.1)
        still_enabled = DeviceStatus(1.0, current_ceiling, True, 19.7, 5.1)
        with (
            patch.dict(
                os.environ,
                {"DPS150_ALLOW_OUTPUT_ON_TEST": "1"},
                clear=True,
            ),
            patch(
                "builtins.input",
                side_effect=["NO LOAD CONNECTED", "1.0", "0.1"],
            ),
            patch("manual_output_on.DPS150") as device_factory,
        ):
            device = device_factory.return_value
            device.get_status.side_effect = [
                initial,
                capped,
                enabled,
                still_enabled,
            ]
            with self.assertRaisesRegex(RuntimeError, "still reports output enabled"):
                manual_output_on.main()

        self.assertEqual(device.set_output.call_args_list, [call(True), call(False)])
        device.set_voltage.assert_called_once_with(1.0)
        device.set_current.assert_called_once_with(current_ceiling)
        device.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
