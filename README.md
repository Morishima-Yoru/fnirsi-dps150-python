# FNIRSI DPS150 Python Library

A synchronous Python (`>=3.10`) control library for the FNIRSI DPS150 programmable DC power supply over USB virtual serial (`pyserial`, PEP 561 `py.typed`).

Protocol behavior is reverse-engineered and not an official FNIRSI specification. Behavior and limits documented below reflect checks performed on a target `DPS-150` (`HW V1.0`, `FW V1.2`, USB `VID=0x2E3C`, `PID=0x5740`) and are not cross-firmware guarantees.

## Installation

Install from a built wheel (recommended for end users) or from source:

```powershell
pip install fnirsi_dps150-0.1.0-py3-none-any.whl
# or from source checkout:
uv pip install .
```

## Quickstart

Instantiate `DPS150` using either a COM port (`port="COM3"`) or a USB VCP serial number (`serial_number="10F5D04E4486"`). Both selectors are mutually exclusive; construction performs no serial I/O (`serial_number` inspects enumerated `VID=0x2E3C` port metadata case-insensitively without opening any port). Use `find_ports()` to discover `VID=0x2E3C:PID=0x5740` ports on the host.

```python
from fnirsi_dps150 import DPS150, find_ports

# Option 1: auto-discover port or pass explicit COM port
port = (find_ports() or ("COM3",))[0]
with DPS150(port=port, timeout=1.0) as device:
    info = device.get_device_info()
    snapshot = device.get_snapshot()

# Option 2: connect by USB VCP serial number
with DPS150(serial_number="10F5D04E4486", timeout=1.0) as device:
    status = device.get_status()
    measurements = device.get_measurements()
```

- `open()` sends the session handshake (`C1 00 01`) without changing setpoints or output state.
- `close()` sends the session disconnect frame (`C1 00 00`) by default to unlock the front panel and silence unsolicited telemetry without altering output state (pass `keep_locked=True` to skip).
- Setpoint writes (`set_voltage()`, `set_current()`, `set_setpoints()`) never enable output; output requires an explicit `set_output(True)` / `set_output(False)` call.
- Every getter/setter performs explicit synchronous frame exchange with a 50 ms post-write gap, stale RX buffer flush, and `0xF0 0xA1` stream resynchronization.

## Verified Capabilities & Limits

Tested on `DPS-150` (`HW V1.0`, `FW V1.2`):

- **Telemetry & snapshots**: `get_status()`, full 139-byte `get_snapshot()`, `get_measurements()`, `get_input_voltage()`, `get_temperature()`, `get_regulation_mode()` (`RegulationMode.CV` / `CC`), and `get_device_info()`.
- **Stored presets (`M1`–`M6`)**: `get_preset(slot)`, `get_presets()`, and `set_preset(slot, Preset(...))` (requires output OFF; updates stored slot fields without loading them into active setpoints; persisted across a full power cycle after a clean `close()`).
- **System settings & metering**:
  - Display brightness (`0`–`14`, physical max `14` observed on target; output OFF required for writes).
  - Buzzer volume (`get_volume()`, `set_volume()`, `0`–`10` where `0` is muted; output OFF required for writes).
  - Accumulated `Ah`/`Wh` metering (`get_metering()`, `DeviceSnapshot.metering`, `set_metering_enabled()`, `reset_metering()` via `0 -> 1` transition; works with output ON or OFF).
- **Protections**:
  - `get_protection_limits()` reads device-reported ceilings (`30.0 V`, `~5.1 A`, `150.0 W`, `99.0 °C`, `30.0 V` on target).
  - `get_protection_status_code()` returns the raw protection byte; `get_protection_status()` maps verified codes `0`–`5` (`ProtectionStatus.NONE`, `OVP`, `OCP`, `OPP`, `OTP`, `LVP`) and returns `None` for unverified bytes.
  - Threshold getters/setters (`set_over_voltage_threshold()`, `set_over_current_threshold()`, `set_over_power_threshold()`, `set_over_temperature_threshold()`, `set_low_voltage_threshold()`, plus grouped `get_protection_settings()` / `set_protection_settings()` for OPP/OTP/LVP) enforce output OFF and validate wire float32 values against device ceilings.
  - Observed clearing behavior: LVP auto-cleared when its threshold was restored; latched OVP/OCP/OPP/OTP cleared when output was re-enabled (`~0.7 s` ramp).
- **Excluded / unsupported**: DFU (`0xC0`), USB VCP baud switching (`0xB0`), native preset load (`load_preset()`), high-power characterization, and external-meter calibration accuracy claims.

## Examples

Runnable scripts in `examples/` support both `--port` and `--serial-number`:

- **Read-only inspection** (no writes, no output change):
  ```powershell
  uv run python examples/read_snapshot.py
  uv run python examples/read_snapshot.py --serial-number 10F5D04E4486
  ```
- **Output-OFF configuration** (dry-run by default; pass `--apply` with output OFF to write, read back, and restore unless `--keep` is set):
  ```powershell
  uv run python examples/configure_and_read.py
  uv run python examples/configure_and_read.py --apply --brightness 10 --volume 1
  ```
- **Controlled low-power output and metering** (requires `--confirm-load`, enforces conservative caps `<= 10.0 V` and `<= 0.10 A`, and turns output OFF + restores initial setpoints in `finally`):
  ```powershell
  uv run python examples/controlled_output_metering.py --confirm-load --voltage 5.0 --current 0.05
  ```

## Development

Use CPython `>=3.10` and `uv` (see [AGENTS.md](AGENTS.md) for coding and safety rules):

```powershell
uv sync
uv run --locked python -m unittest discover -s tests -v
uv run --locked flake8 src tests examples
uv build
```
