# FNIRSI DPS150 Python Library

A small, synchronous Python library for controlling the FNIRSI DPS150 over USB virtual serial. It provides an explicit serial session and a safe status read; hardware-dependent controls are added only after verification on the target unit.

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
handshake, not a setpoint or output-control command. `get_status()` explicitly
reads whether the output is enabled. Closing the serial port sends no device
command.

```python
from fnirsi_dps150 import DPS150

with DPS150(port="COM3", timeout=1.0) as device:
    status = device.get_status()

print(status.output_enabled)
```

The library does not start a background reader. The status query requires the
session handshake observed on the tested unit. Other device-specific behavior
remains unsupported until verified.

Automated tests use a fake serial port and never enable output. A hardware
test that enables output must remain a separate manual opt-in, assume no load,
require explicit operator confirmation and caller-provided voltage/current
ceilings, verify only command and state readback, and attempt to turn output
off afterward.

## Worktree order

Use the integration checkout for tickets 01 and 02. After ticket 02 is
integrated, create one worktree per ticket for 03–06, all based on that same
integration commit. Keep each worktree on its own branch and do not modify
the shared serial/protocol transport in those parallel slices. Integrate all
four before ticket 07.
