# Coding Style and Repository Rules

## Project Scope
- `fnirsi-dps150` is a small, synchronous Python hardware-control library for the FNIRSI DPS150 programmable DC power supply over its USB virtual serial port (VCP).
- Runtime dependency is `pyserial` only. Do not add GUI, CLI, background worker threads, telemetry polling loops, YAML configuration, or external logging frameworks unless a concrete library specification requires them.
- Keep wire framing, checksums, pacing, RX flushing, stream resynchronization, and pySerial I/O private behind the high-level `:class:DPS150` facade and `find_ports()` helper.

## Repository Layout
- `src/fnirsi_dps150/__init__.py`: Public package API (`__all__`).
- `src/fnirsi_dps150/device.py`: Synchronous `DPS150` interface and `find_ports()`.
- `src/fnirsi_dps150/models.py`: Frozen slotted result dataclasses (`DeviceStatus`, `DeviceSnapshot`, `Measurements`, `MeteringReadings`, `DeviceInfo`, `Preset`, `ProtectionSettings`, `ProtectionLimits`, `SystemSettings`).
- `src/fnirsi_dps150/definitions/exceptions.py`: Exception hierarchy rooted at `DPS150Error`.
- `src/fnirsi_dps150/definitions/namespace.py`: Public enums (`ProtectionStatus`, `RegulationMode`) and private protocol constants and snapshot byte offsets.
- `src/fnirsi_dps150/_protocol.py`: Private frame encoder/decoder and checksum validation.
- `src/fnirsi_dps150/_transport.py`: Private pySerial transport (`115200` 8N1, 50 ms post-write command gap, stale RX buffer flush, and `0xF0 0xA1` resynchronization).
- `src/fnirsi_dps150/py.typed`: PEP 561 type-marker file.
- `tests/`: Offline fake-serial unit tests (`test_device.py`, `test_protocol.py`).
- `examples/`: Runnable usage scripts covering read-only inspection, output-OFF configuration, and opt-in controlled output/metering.

## Language, Tooling, and Verification
- Target CPython `>=3.10` compatibility for all runtime, test, and example code.
- Use `uv` to manage Python environments (`uv sync` / `uv run --locked ...`).
- Use standard 4-space indentation (PEP 8) and keep `src/`, `tests/`, and `examples/` `flake8`-compliant (`.flake8` sets `extend-ignore = E501`).
- Run all repository checks before committing:
  - `uv run --locked python -m unittest discover -s tests -v`
  - `uv run --locked flake8 src tests examples`
  - `uv build`

## Naming Conventions
- Variables, functions, and methods: descriptive `snake_case` with explicit verbs for functions.
- Classes, dataclasses, enums, and exceptions: noun-based `PascalCase`.
- Module constants and `Final` values: `UPPER_CASE`, explicitly annotated with `Final[...]`.
- Private classes, helpers, and attributes: `_snake_case` (or `_PascalCase` for private types) with one leading underscore.
- Name-mangled lifecycle hooks (`__snake_case`): reserve only for initialization/bootstrap helpers if needed.
- Generic type variables (when used): suffix with `T` (for example, `StateT`). Use `TypeVar` and `Generic` rather than PEP 695 syntax so runtime code stays compatible with Python 3.10.

## Type Hints and Docstrings
- Avoid `typing.Any` in type hints; prefer `object` or generics.
- Use `A | B` and `A | None` instead of `Union` / `Optional`, and use built-in generic collections (`tuple[Preset, ...]`, `list[str]`, `dict[str, int]`). Include `from __future__ import annotations` in Python 3.10 modules using modern union syntax in annotations.
- For explicit generic aliases, use `TypeAlias` from `typing` with a Python 3.10-compatible `TypeVar`.
- Write Google-style docstrings for all public and private modules, classes, methods, and helper functions:
  - Include `Args:`, `Returns:`, and `Raises:` sections where appropriate.
  - Use ``:class:`Foo``` (or ``:class:`~fnirsi_dps150.Foo```) to cross-reference classes and exceptions.
  - Include an `Attributes:` section on classes that expose public attributes or key private state.

## Exception Handling and Logging
- Root all library exceptions at `DPS150Error` in `src/fnirsi_dps150/definitions/exceptions.py`, subclassed by domain (`DPS150CommunicationError`, `DPS150TimeoutError`, `DPS150ConnectionError`, `DPS150ProtocolError`).
- Never swallow exceptions silently in library code; preserve tracebacks with `raise NewException(...) from error`.
- Use `contextlib.suppress(DPS150Error)` only in explicit safe cleanup paths (such as closing a port after an `open()` handshake error or context-manager `__exit__` teardown while another exception is propagating).
- Never call `print()` inside `src/fnirsi_dps150/`. If library logging is ever introduced, use standard library `_logger = logging.getLogger(__name__)` without installing global handlers.

## Hardware Safety and Evidence Discipline
- Protocol behavior is reverse-engineered, not an official FNIRSI specification. Document verified target behavior and observed limits in `README.md` before exposing public APIs, and never present single-unit observations (COM64, HW V1.0, FW V1.2) as cross-firmware guarantees.
- Never send DFU/bootloader commands (`0xC0`) or unsupported baud-rate switching commands (`0xB0`).
- Automated unit tests (`tests/test_*.py`) must run strictly offline using fake serial adapters and must never open hardware or enable output.
- Object construction, `open()`, `close()`, setpoint writes, and preset writes must never alter output state. `close()` sends `C1 00 00` by default to unlock the front panel and stop unsolicited telemetry (callers may pass `keep_locked=True`).
- Writes to presets, display brightness (`0`–`14`), buzzer volume (`0`–`10`), and protection thresholds must verify output is disabled and validate exact float32 wire values against device-reported limits/ceilings without silent clamping or truncation.
- Any hardware script or example that enables output must require explicit user opt-in/confirmation, enforce clear voltage/current ceilings, shut off and confirm output OFF in `finally`, and restore original setpoints only after OFF is confirmed.
