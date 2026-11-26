# FNIRSI DPS150 Python Library

A small, synchronous Python library for controlling the FNIRSI DPS150 over USB virtual serial. It provides explicit status and measurement reads, setpoint controls, and a separate output-control method. Hardware-dependent behavior is documented only to the extent verified on the target unit.

## Project documents

- [Library specification](DPS150-LIBRARY-SPEC.md)
- [Protocol research and source comparison](DPS150-PROTOCOL.md)
- [Agent and coding instructions](AGENTS.md)
- Tickets: `.scratch/fnirsi-dps150-python/issues/`

Protocol details are reverse-engineered and not an official FNIRSI specification. Device-specific behavior must be verified before claiming support.

## Development setup

Use CPython 3.10 or newer and `uv`. The checked-in `.python-version` selects Python 3.10 for minimum-version checks.

Install the library from this checkout with:

```powershell
uv pip install .
```

For development, sync the project and run its checks:

```powershell
uv sync
uv run python -m unittest discover -s tests -v
uv run flake8 src tests
uv build
```

## Usage

Construction performs no I/O. `open()` sends the target-observed session
handshake, not a setpoint or output-control command. `get_status()` and
`get_measurements()` explicitly read typed snapshots. Setpoint writes do not
enable output; changing output requires an explicit `set_output()` call.
Closing the serial port sends no device command.

```python
from fnirsi_dps150 import DPS150

with DPS150(port="COM3", timeout=1.0) as device:
    status = device.get_status()
    measurements = device.get_measurements()
    info = device.get_device_info()
    input_voltage = device.get_input_voltage()
    temperature = device.get_temperature()
    mode = device.get_regulation_mode()
    preset = device.get_preset(1)
    settings = device.get_system_settings()
    protections = device.get_protection_settings()
    device.set_voltage(5.0)
    device.set_current(1.0)

print(status.output_enabled, measurements.output_voltage)
print(info, input_voltage, temperature, mode)
print(preset, settings, protections)
```

The library does not start a background reader. On the tested unit, status
responses can be interleaved with other valid field frames; `get_status()`
matches the requested snapshot within one finite timeout without retrying the
request. Setpoint limits are checked against the device-reported values using
the exact float32 values sent on the wire. A separate, manually gated no-load
test on COM64 verified that output control (`SET type 219`) changes the
reported state ON and then OFF. The latest bounded run and setpoint restoration
are described below. This verifies command/state readback only—not loaded
regulation, current delivery, 100 W capability, or emergency-shutdown
reliability. The nonzero measurement field mapping is based on
reverse-engineered sources; only zero measurements were observed on the target
unit while output was OFF.

COM64 reads also verified input voltage (type 192), temperature (type 196),
device identity/version fields (types 222–224), and regulation mode (type 221,
reported as CV). `get_input_voltage()`, `get_temperature()`,
`get_device_info()`, and `get_regulation_mode()` expose those reads as
high-level values. These readings are target-specific, not a cross-firmware
guarantee.

On COM64, read/write access to all six stored preset slots was verified while
output was OFF. `get_preset(slot)` and `set_preset(slot, Preset(...))` access
the device's stored voltage/current fields; `set_preset()` does not load a slot
into the active setpoints. Its two writes are not atomic, and persistence
across a device power cycle is unverified. No native preset-load operation was
identified, so the library exposes no `load_preset()` method.

The verified system-setting subset is brightness (0–10) and metering enable.
`get_system_settings()` reads only those fields; `set_brightness()` and
`set_metering_enabled()` require output OFF. Volume/buzzer was excluded from
this support scope. Capacity/energy types returned zero, but their semantics
and write behavior remain unverified and are not exposed. OPP/OTP/LVP thresholds
are exposed by `get_protection_settings()` and `set_protection_settings()`;
COM64 reversible output-OFF writes were read back and restored. The setter
writes three fields separately, is not atomic, and does not test protection
trips. OVP/OCP remain unsupported and outside this scope. Native preset loading
and baud-changing APIs remain omitted because no safe target-verified operation
or recovery path is established. See the target-specific evidence and raw
payloads in [`DPS150-PROTOCOL.md`](DPS150-PROTOCOL.md).

Automated tests use a fake serial port and never enable output. A hardware
test that enables output must remain a separate manual opt-in, assume no load,
require explicit operator confirmation and caller-provided voltage/current
ceilings, verify only command and state readback, and attempt to turn output
off afterward. The gated helper is not part of default test discovery. It
temporarily caps the setpoints while output is OFF, rounds float32 values down
so they never exceed the supplied ceilings, and restores the original values
only after OFF is confirmed. On COM64, the approved no-load check used 1.0 V /
0.1 A ceilings, verified ON and OFF state readback, restored `12.0 V` / `5.0 A`,
and finished with output OFF. This does not test loaded regulation/current
delivery. To run it deliberately in PowerShell:

```powershell
$env:DPS150_ALLOW_OUTPUT_ON_TEST = "1"
uv run python tests/manual_output_on.py
```

It requires the exact no-load confirmation and ceilings before opening COM64
(or the port in `DPS150_PORT`). Setpoints are temporarily changed to stay
within those ceilings and restored after output OFF is confirmed.

## Worktree order

Use the integration checkout for tickets 01 and 02. After ticket 02 is
integrated, create one worktree per ticket for 03–06, all based on that same
integration commit. Keep each worktree on its own branch and do not modify
the shared serial/protocol transport in those parallel slices. Integrate all
four before ticket 07.
