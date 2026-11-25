# 05: Add verified non-baud system settings

**What to build:** A caller can read or change the documented non-baud settings that are confirmed to work on the target unit, including any supported brightness, volume, metering, capacity, and energy fields.

**Blocked by:** 02 — Deliver core power control and readback.

**Status:** ready-for-agent

- [ ] Each supported setting's type, encoding, units, range, and read/write semantics are verified against the target unit.
- [ ] Only verified fields are presented as supported; unknown or unsupported fields fail explicitly.
- [ ] Fake-serial tests cover the confirmed field encodings and validation without device access.
- [ ] Hardware writes are opt-in, with documented recovery steps; settings operations do not change output state.
