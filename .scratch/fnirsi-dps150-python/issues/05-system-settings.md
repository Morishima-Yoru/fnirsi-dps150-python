# 05: Add verified non-baud system settings

**What to build:** A caller can read or change the documented non-baud settings that are confirmed to work on the target unit, including any supported brightness, volume, metering, capacity, and energy fields.

**Blocked by:** target-unit verification of remaining fields and behavior for GET/SET types 215, 217, and 218.

**Status:** partial — brightness and metering verified; other settings unsupported

On COM64 with output OFF, brightness (type 214) read as 10 and metering (type 216) read as disabled. Brightness writes of 9 and 0 and a metering enable write of 1 all read back correctly and were restored to 10/disabled. Output remained OFF and active setpoints remained unchanged. Volume/buzzer (type 215) was not queried or written during this validation. Capacity/energy types 217/218 returned raw zero values but their semantics and writable behavior remain unverified.

- [x] Verify brightness and metering labels, byte encodings, and read semantics against the target and source comparison. Target-tested brightness levels were 0, 9, and 10; metering states 0 and 1.
- [x] Verify reversible SET/readback for brightness and metering, including output remaining OFF and exact restoration of prior values.
- [x] Add `get_system_settings()`, `set_brightness()`, and `set_metering_enabled()` with fake-serial tests and an output-OFF write guard.
- [ ] Volume/buzzer was excluded; capacity and energy have raw GET observations only. These fields remain outside the public API until independently verified.
- [x] Hardware writes were separately authorized, kept outside the default test suite, and restored; recovery observations are recorded above and in `DPS150-PROTOCOL.md`.
