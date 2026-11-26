# 05: Add verified non-baud system settings

**What to build:** A caller can read or change the documented non-baud settings that are confirmed to work on the target unit, excluding buzzer/volume.

**Blocked by:** target-unit verification of capacity/energy semantics and any write behavior for GET/SET types 217 and 218. Volume/buzzer type 215 is excluded.

**Status:** partial — brightness/metering verified; capacity/energy unsupported

On COM64 with output OFF, brightness (type 214) read as 10 and metering (type 216) read as disabled. Brightness writes of 9 and 0 and a metering enable write of 1 all read back correctly and were restored to 10/disabled. Output remained OFF and active setpoints remained unchanged. No direct GET/SET request for volume/buzzer type 215 was sent in this validation. Capacity/energy types 217/218 returned raw zero values but their semantics and writable behavior remain unverified.

- [x] Verify brightness and metering labels, byte encodings, and read semantics against the target and source comparison. Target-tested brightness levels were 0, 9, and 10; metering states 0 and 1.
- [x] Verify reversible SET/readback for brightness and metering, including output remaining OFF and exact restoration of prior values.
- [x] Add `get_system_settings()`, `set_brightness()`, and `set_metering_enabled()` with fake-serial tests and an output-OFF write guard.
- [x] Volume/buzzer remains excluded. Capacity/energy types 217/218 returned zero raw values; their semantics and writable behavior remain unverified, so they remain outside the public API.
- [x] Hardware writes were separately authorized, kept outside the default test suite, and restored; recovery observations are recorded above and in `DPS150-PROTOCOL.md`.
