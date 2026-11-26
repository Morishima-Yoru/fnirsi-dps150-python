# FNIRSI DPS150 Python Library Specification

## Status

Implementation is complete for behavior verified on the target unit. Output enable/disable command state readback was verified in a separately gated no-load test; loaded regulation, current delivery, and nonzero measurement semantics remain unconfirmed. Other unverified hardware-dependent operations remain intentionally unexposed. This specification remains a draft for review, not an official FNIRSI device protocol specification.

## Purpose

Provide a small, synchronous Python module for scripts and other applications to control a FNIRSI DPS150 through its USB virtual COM port. A GUI may call the library's read methods when it needs data; the library itself does not run a monitor or background polling loop.

The protocol research in [DPS150-PROTOCOL.md](./DPS150-PROTOCOL.md#L3) compares four reverse-engineered implementations. It is evidence for implementation and tests, not an independently verified hardware specification.

## Package and runtime

- Distribution name: `fnirsi-dps150`.
- Import package: `fnirsi_dps150`.
- Main public class: `DPS150`.
- Minimum supported runtime: CPython 3.10.
- Runtime serial dependency: pySerial.
- Build/installable from this workspace; no public PyPI release or CLI is in scope.
- Support Windows, Linux, and macOS where pySerial and a compatible USB VCP driver are available.
- The workspace `AGENTS.md` now sets Python 3.10 compatibility and avoids requiring PEP 695 syntax. The external `PYTHON.md` remains unchanged.

## Scope

### Included

- USB virtual serial (VCP/COM) transport through pySerial. Physical UART-TTL pinout and electrical compatibility are not claimed.
- Synchronous, high-level controls for output voltage/current setpoints and explicit output enable/disable.
- Explicit read methods for values and status. Callers decide when to read; no telemetry scheduler, watch loop, GUI, callback stream, or background thread.
- Target-verified reads/writes for preset slot values and the brightness/metering settings subset. Native preset loading, volume/buzzer, capacity/energy writes, OVP/OCP controls, and baud changing remain unsupported until their behavior is verified.
- A private protocol implementation that handles framing, checksums, parsing, serial I/O, and device-specific behavior. Raw packet operations are not a stable public interface.
- Typed dataclasses for structured read results.

### Excluded

- CLI, GUI, or monitor application.
- A public raw-frame/command API or general profile system for unrelated firmware variants.
- Claims of compatibility with all DPS150 firmware or related models.
- Emulating native preset load/save by merely writing active setpoints.
- Supporting physical UART-TTL wiring without verified pinout and electrical specifications.

## Public interface

The proposed interface is a single device module with a small caller-facing surface. Construction stores connection settings but performs no I/O. Both context-manager use and explicit `open()` / `close()` are supported.

```python
from fnirsi_dps150 import DPS150

device = DPS150(port="COM3")
with device:
    device.set_voltage(5.0)
    device.set_current(1.0)
    preset = device.get_preset(1)
    settings = device.get_system_settings()
    status = device.get_status()
    device.set_output(True)
```

The example illustrates the intended interface shape. Hardware evidence is feature-specific; see [DPS150-PROTOCOL.md](./DPS150-PROTOCOL.md#L3) for the tested command/state limits.

Interface requirements:

- Setpoint inputs are finite Python `float` values in volts and amperes.
- Reject non-finite and out-of-range inputs with an explicit exception; never silently clamp or truncate. Enforce limits only when supported by verified device information.
- Setting a setpoint never enables the output. Output changes require an explicit method call.
- Opening or closing the serial connection never changes output state.
- Read operations are explicit and synchronous. They return typed dataclasses rather than loosely specified dictionaries or tuples.
- Preset slot and verified system-setting writes require output disabled; preset writes change stored fields only and never simulate loading through active setpoints.
- Communication, frame/checksum, unsupported-feature, and invalid-input failures are surfaced explicitly. Preserve underlying exception causes; do not return success-shaped defaults.
- Use a finite configurable I/O timeout. Do not automatically retry reads or writes; callers may make their own retry decision.

## Module and seam

The external seam is the `DPS150` module interface: callers should not need to construct frames, calculate checksums, correlate responses, or know device-specific payload layouts. Keep that behavior in the implementation so the module has depth for scripts and GUI callers.

Use a private serial-adapter seam inside the implementation. The production adapter uses pySerial; tests use a fake adapter at the same seam. Do not expose the adapter or raw protocol as a second public interface unless a later requirement demonstrates a real caller need.

## Connection and protocol behavior

- Initial host serial settings: 115200 baud, 8 data bits, no parity, 1 stop bit, and no RTS/CTS hardware flow control. These settings appear in the source comparison, but flow-control claims conflict; validate against the target unit before treating them as confirmed device requirements ([protocol notes](./DPS150-PROTOCOL.md#L5)).
- The target is the user's testable DPS150 unit. Do not claim that its behavior establishes cross-firmware compatibility.
- The common frame shape and checksum are documented in [DPS150-PROTOCOL.md](./DPS150-PROTOCOL.md#L7). Keep the encoder, decoder, and serial adapter private to the implementation.
- Do not assume fixed response timing, request/response correlation, unsolicited telemetry cadence, or a specific error reply unless hardware tests establish it.
- Baud-change support is conditional on verifying both the device command and host reconnection/resynchronization behavior.

## Hardware-dependent features

The reference implementations conflict on some operations. Test the actual device before claiming these features work:

- **OVP/OCP:** references disagree between one-byte flags and float32 thresholds ([protocol notes](./DPS150-PROTOCOL.md#L53)). Expose only the protection semantics confirmed on the target device; do not silently select or auto-detect a dialect.
- **Presets:** COM64 verified GET/SET readback for all six native voltage/current slot fields while output was OFF. `get_preset()` and `set_preset()` expose stored values only. No native load command or power-cycle persistence was verified, so there is no load method and no claim that writing a slot applies it to active setpoints.
- **System settings:** COM64 verified brightness read/write (target-tested levels 0, 9, and 10) and metering enable read/write (0/1), with restoration and output OFF. Volume/buzzer was excluded; capacity/energy have raw GET observations only and no public API. OVP/OCP writes and baud changing remain unsupported because their semantics or recovery paths are unresolved.
- **Limits and timing:** device-enforced ranges, response timing, error replies, and cross-firmware behavior remain unverified until measured.

## Safety and side effects

- Normal unit tests must never enable device output.
- Hardware writes are opt-in and separated from ordinary tests.
- An output-ON hardware check is a separate manual opt-in. It requires caller-provided voltage/current ceilings and explicit confirmation, assumes no external load, verifies command/state readback only, and attempts to turn output off afterward. It does not verify loaded regulation or current delivery.
- Preset and system-setting hardware writes are tested separately with output OFF; these write methods reject an enabled-output status.
- Do not automatically alter output state during construction, connection, disconnection, or context-manager cleanup.

## Validation and acceptance criteria

1. Protocol framing, checksum, partial-frame handling, parsing, input validation, and error propagation are covered by tests using a fake serial adapter; these tests do not require hardware.
2. The package installs locally and its source remains compatible with CPython 3.10.
3. Opening and closing the connection does not change output state; setpoint writes do not enable output.
4. Device writes and reads for setpoints, output state, protections, presets, and system fields are verified on the target unit before being described as supported.
5. Preset slot methods are included only for verified native stored fields. A load method is included only if a native load operation is verified; active setpoint writes are never presented as preset loading.
6. Hardware tests are not part of the default automated test run. Any output-ON check requires explicit opt-in and the safeguards above.
7. Documentation separates observed implementation behavior from confirmed target-device behavior and makes unverified limits clear.

## Sources and unresolved facts

Use [DPS150-PROTOCOL.md](./DPS150-PROTOCOL.md#L53) as the source comparison. It records, among other disagreements, baud index 4 versus 5 for 115200, OVP/OCP payload formats, disconnect payloads, GET payloads, RTS/CTS settings, and preset/system-field interpretation. Resolve only the target device's behavior through safe hardware tests; do not present reverse-engineered claims as official FNIRSI guarantees ([unresolved facts](./DPS150-PROTOCOL.md#L66)).
