# 04: Support native preset operations when available

**What to build:** A caller can use only the preset read, save, and load operations that the target device natively supports. Preset loading must not be emulated by writing the preset values as current output setpoints.

**Blocked by:** 02 — Deliver core power control and readback.

**Status:** ready-for-agent

- [ ] Native preset slot read/write and load/save semantics are verified on the target unit before being described as supported.
- [ ] Public operations correspond to confirmed device-native preset behavior; the API does not present active setpoint writes as a native load command.
- [ ] Fake-serial tests cover any confirmed preset frame formats without enabling output in the default test suite.
- [ ] If native load/save behavior is absent or cannot be verified, no substitute preset API is added; the result and supporting evidence are documented.
