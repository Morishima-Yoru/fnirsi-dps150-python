# 04: Support native preset operations when available

**What to build:** A caller can use only the preset read, save, and load operations that the target device natively supports. Preset loading must not be emulated by writing the preset values as current output setpoints.

**Blocked by:** 02 — Deliver core power control and readback.

**Status:** partial — native slot read/write verified; loading unsupported

- [x] GET/SET fields for all six native preset slots were verified on COM64 with output OFF. Each slot's values were changed temporarily to `5.25 V` / `1.25 A`, read back, and restored to `5.0 V` / `1.0 A`.
- [x] After each slot test, output remained OFF and active setpoints remained `12.0 V` / `5.0 A`.
- [x] Fake-serial tests cover first/last slot reads, slot writes, invalid slot inputs, and device-reported limits; default tests never enable output.
- [x] Public `get_preset()` / `set_preset()` operations access stored slot fields only. `set_preset()` does not change active setpoints or emulate loading.
- [ ] A native slot-load operation and persistence across device power-cycle remain unverified; no `load_preset()` API is exposed.

### Current evidence (COM64, output OFF)

- A read-only GET sweep returned a matching four-byte payload for every type 197–208: types 197, 199, 201, 203, 205, and 207 each returned `0000a040`; types 198, 200, 202, 204, 206, and 208 each returned `0000803f`.
- The reversible slot SET/readback test confirmed the target field mapping and write behavior. It did not test a native load command or persistence across device power-cycle.

### Missing proof

- Identify and verify a device-native load command, if one exists, without emulating it by writing active setpoints.
- Verify persistence across a device power-cycle before documenting durable save behavior.
