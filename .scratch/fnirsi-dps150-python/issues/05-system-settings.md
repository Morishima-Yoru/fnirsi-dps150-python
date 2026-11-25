# 05: Add verified non-baud system settings

**What to build:** A caller can read or change the documented non-baud settings that are confirmed to work on the target unit, including any supported brightness, volume, metering, capacity, and energy fields.

**Blocked by:** target-unit verification of the fields and behavior for GET/SET types 214–218.

**Status:** blocked — unsupported on current evidence; no settings API was added.

The target-unit evidence records GET payload lengths of 1, 1, 1, 4, and 4 bytes for types 214–218. It does not identify the settings, establish units or accepted ranges, or verify SET behavior and readback. Protocol-reference labels such as brightness, volume, metering, capacity, and energy are not sufficient evidence of target behavior. No setting write was attempted. Keep these settings unsupported until the evidence gaps below are resolved.

- [x] Reviewed the available evidence and confirmed it establishes only raw GET payload lengths; no settings API was added.
- [ ] Verify each target field's label, encoding, units, valid values/range, and read semantics.
- [ ] Verify each setting's SET and readback effects on the target, including that output state is unchanged and the prior value can be restored.
- [ ] Add only verified fields, with fake-serial tests for their confirmed encodings and validation; leave unverified fields unsupported.
- [ ] Keep any future hardware writes opt-in and document recovery/restoration steps.
