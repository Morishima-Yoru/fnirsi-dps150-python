"""Offline tests for the manual output-enable safety gate."""

import os
import unittest
from unittest.mock import call, patch

import manual_output_on
from fnirsi_dps150 import DeviceStatus


class ManualOutputOnTests(unittest.TestCase):
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

    def test_current_setpoints_must_fit_operator_ceilings(self) -> None:
        status = DeviceStatus(5.0, 0.5, False, 20.0, 5.0)
        with (
            patch.dict(
                os.environ,
                {"DPS150_ALLOW_OUTPUT_ON_TEST": "1"},
                clear=True,
            ),
            patch(
                "builtins.input",
                side_effect=["NO LOAD CONNECTED", "4", "1"],
            ),
            patch("manual_output_on.DPS150") as device_factory,
        ):
            device = device_factory.return_value
            device.get_status.return_value = status
            with self.assertRaisesRegex(RuntimeError, "voltage setpoint"):
                manual_output_on.main()

        self.assertEqual(device.set_output.call_args_list, [call(False)])
        device.close.assert_called_once_with()

    def test_output_is_turned_off_after_state_readback_failure(self) -> None:
        initial = DeviceStatus(5.0, 0.5, False, 20.0, 5.0)
        final = DeviceStatus(5.0, 0.5, False, 20.0, 5.0)
        with (
            patch.dict(
                os.environ,
                {"DPS150_ALLOW_OUTPUT_ON_TEST": "1"},
                clear=True,
            ),
            patch(
                "builtins.input",
                side_effect=["NO LOAD CONNECTED", "5", "1"],
            ),
            patch("manual_output_on.DPS150") as device_factory,
        ):
            device = device_factory.return_value
            device.get_status.side_effect = [initial, RuntimeError("read failed"), final]
            with self.assertRaisesRegex(RuntimeError, "read failed"):
                manual_output_on.main()

        self.assertEqual(device.set_output.call_args_list, [call(True), call(False)])
        device.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
