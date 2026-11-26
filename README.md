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
    preset = device.get_preset(1)
    settings = device.get_system_settings()
    device.set_voltage(5.0)
    device.set_current(1.0)

print(status.output_enabled, measurements.output_voltage)
print(preset, settings)
```

The library does not start a background reader. On the tested unit, status
responses can be interleaved with other valid field frames; `get_status()`
matches the requested snapshot within one finite timeout without retrying the
request. Setpoint limits are checked against the device-reported values using
the exact float32 values sent on the wire. A separate, manually gated no-load
test on COM64 verified that output control (`SET type 219`) changed the
reported state ON and then OFF using `12 V` / `5 A` ceilings, without changing
the existing setpoints. This verifies command/state readback only—not loaded
regulation, current delivery, 100 W capability, or emergency-shutdown
reliability. The nonzero measurement field mapping is based on
reverse-engineered sources; only zero measurements were observed on the target
unit while output was OFF.

On COM64, read/write access to all six stored preset slots was verified while
output was OFF. `get_preset(slot)` and `set_preset(slot, Preset(...))` access
the device's stored voltage/current fields; `set_preset()` does not load a slot
into the active setpoints. Its two writes are not atomic, and persistence
across a device power cycle is unverified. No native preset-load operation was
identified, so the library exposes no `load_preset()` method.

The verified system-setting subset is brightness (0–10) and metering enable.
`get_system_settings()` reads only those fields; `set_brightness()` and
`set_metering_enabled()` require output OFF. Volume/buzzer was excluded from
this validation, and capacity/energy writes remain unsupported. OVP/OCP and
baud-changing APIs are also omitted because their SET semantics or recovery
paths remain unverified. See the target-specific evidence and raw payloads in
[`DPS150-PROTOCOL.md`](DPS150-PROTOCOL.md).

Automated tests use a fake serial port and never enable output. A hardware
test that enables output must remain a separate manual opt-in, assume no load,
require explicit operator confirmation and caller-provided voltage/current
ceilings, verify only command and state readback, and attempt to turn output
off afterward. The gated helper is not part of default test discovery. Its
COM64 run used the unchanged `12.0 V` / `5.0 A` setpoints as ceilings and
confirmed OFF afterward. To run it deliberately in PowerShell:

```powershell
$env:DPS150_ALLOW_OUTPUT_ON_TEST = "1"
uv run python tests/manual_output_on.py
```

It requires the exact no-load confirmation and ceilings before opening COM64
(or the port in `DPS150_PORT`). It does not change setpoints or test loaded
regulation/current delivery.

## Worktree order

Use the integration checkout for tickets 01 and 02. After ticket 02 is
integrated, create one worktree per ticket for 03–06, all based on that same
integration commit. Keep each worktree on its own branch and do not modify
the shared serial/protocol transport in those parallel slices. Integrate all
four before ticket 07.
