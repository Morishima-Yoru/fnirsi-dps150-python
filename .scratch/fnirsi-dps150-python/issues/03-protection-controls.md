# 03: Add verified OVP/OCP controls

**What to build:** A caller can read and configure the over-voltage and over-current protection behavior that is confirmed on the target DPS150. The implementation does not guess between the conflicting flag and float-threshold formats in the reference projects.

**Blocked by:** 02 — Deliver core power control and readback.

**Status:** unsupported-on-current-evidence

- [x] A read-only COM64 sweep of GET types 209–213 returned four-byte payloads: type 209 `0000f041`, 210 `3333a340`, 211 `00001643`, 212 `0000a042`, and 213 `0000a040`. These raw bytes are recorded without assigning semantics.
- [ ] OVP/OCP meanings and GET representations are confirmed. **Unverified:** reference projects conflict between one-byte enable flags and float32 thresholds; the target GET payloads do not resolve the meaning.
- [ ] SET types, payloads, valid ranges, readback behavior, and output-state side effects are confirmed. **Unverified:** no protection SET was tested; do not infer write semantics from GET payload shape.
- [ ] OVP/OCP trip behavior is verified. **Unverified:** no protection trip was tested.
- [x] The follow-up COM64 read repeated the same type 209–213 payloads with output OFF. No protection SET or trip test was attempted because the representation conflict leaves the original enable state and safe restoration path unverified.
- [x] No public protection API or fake protection tests were added; the missing evidence is documented rather than guessed.
- [x] The missing evidence is recorded and the library does not claim protection support on this target/evidence.
