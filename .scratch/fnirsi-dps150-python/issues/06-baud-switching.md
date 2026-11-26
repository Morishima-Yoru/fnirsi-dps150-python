# 06: Safely change baud rate and resynchronize

**What to build:** A caller can change the instrument's baud rate only when the target device's baud index and host reconnection/resynchronization sequence have been verified. Uncertain rate changes are not silently attempted.

**Blocked by:** 02 — Deliver core power control and readback.

**Status:** unsupported on current evidence

- [ ] The baud command, index mapping, and device-side transition are verified on the target unit.
- [ ] The host serial port is switched and resynchronized using a documented, bounded sequence with explicit failure reporting.
- [ ] Tests cover the confirmed command and recovery/error paths without requiring hardware. (Not applicable until the device transition is verified.)
- [x] Because reliable device and host synchronization cannot be verified, the public baud-changing operation is omitted and the limitation is documented below.

## Current evidence

- No baud-change command was sent to the target unit. The hardware evidence records no device/host resynchronization or recovery test.
- The protocol comparison disagrees on the `B0`/type `0` index for 115200: one source says `0x04`; the others say `0x05`. Neither value is verified for the target, so neither is attempted.
- This checkout exposes no public baud-changing operation; the existing connection remains at its configured 115200 baud.
- The follow-up capability validation did not change this evidence; the conflicting index and recovery path remain unresolved.

## Evidence required before future support

1. A source or captured target-unit trace, scoped to the tested device/firmware, that unambiguously identifies the `B0`/type `0` payload for the requested baud and resolves the `0x04` versus `0x05` conflict for 115200. It must also establish when the device applies the change and whether/how it acknowledges it.
2. A controlled target-unit trace recording the pre-change baud and firmware identity, exact command and response (or documented switch behavior), host serial-port baud change, session/resynchronization sequence, and a successful fresh status read at the new rate.
3. A bounded failure/recovery test showing how the host reports a missing or invalid response, returns both host and device to a known baud, and avoids blind retries or silent success.
4. Hardware-free tests for the verified command, host-switch/resynchronization order, successful readback, timeout/error reporting, and the demonstrated recovery path.
