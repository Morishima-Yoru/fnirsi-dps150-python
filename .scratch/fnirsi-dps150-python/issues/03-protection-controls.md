# 03: Add verified OVP/OCP controls

**What to build:** A caller can read and configure the over-voltage and over-current protection behavior that is confirmed on the target DPS150. The implementation does not guess between the conflicting flag and float-threshold formats in the reference projects.

**Blocked by:** 02 — Deliver core power control and readback.

**Status:** ready-for-agent

- [ ] Request/response types, payloads, and protection semantics are verified against the target unit before being exposed as supported.
- [ ] Read and write operations use the confirmed representation and surface unsupported or unverified operations explicitly.
- [ ] Protection writes do not implicitly enable or disable the output.
- [ ] Fake-serial tests cover the confirmed encoding, decoding, and invalid values; hardware writes are opt-in and have documented recovery steps.
- [ ] If the target behavior cannot be verified, the ticket records the missing evidence and the library does not claim the feature is supported.
