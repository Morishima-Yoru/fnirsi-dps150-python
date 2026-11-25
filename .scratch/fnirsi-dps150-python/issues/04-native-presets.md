# 04: Support native preset operations when available

**What to build:** A caller can use only the preset read, save, and load operations that the target device natively supports. Preset loading must not be emulated by writing the preset values as current output setpoints.

**Blocked by:** 02 — Deliver core power control and readback.

**Status:** complete (unsupported on current evidence)

- [ ] Native preset slot read/write and load/save semantics are verified on the target unit before being described as supported. This remains intentionally unverified; the ticket is closed without claiming preset support.
- [x] No public preset operations were added without confirmed device-native behavior; active setpoint writes are not presented as a native load command.
- [x] Not applicable: no preset frame formats are confirmed, so no fake-serial preset tests were added.
- [x] With native load/save behavior unverified, no substitute preset API was added; the read observation and evidence gap are documented below.

### Current evidence (COM64, output OFF)

- A read-only GET sweep returned a matching four-byte payload for every type 197–208: types 197, 199, 201, 203, 205, and 207 each returned `0000a040`; types 198, 200, 202, 204, 206, and 208 each returned `0000803f`.
- No preset SET, save, or load was attempted. The raw GET responses establish only that these types returned four bytes; they do not establish payload meaning, slot mapping, writable/persistent behavior, or native load/save semantics.

### Missing proof

- Confirm which native command(s), if any, save or load a preset and how their effects can be distinguished from ordinary active setpoint writes.
- Verify the slot-to-value mapping, SET payload representation, persistence, and native load/save behavior on the target unit before adding any public preset API or frame tests.
