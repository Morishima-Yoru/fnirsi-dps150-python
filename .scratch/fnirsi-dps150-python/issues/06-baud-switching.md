# 06: Safely change baud rate and resynchronize

**What to build:** A caller can change the instrument's baud rate only when the target device's baud index and host reconnection/resynchronization sequence have been verified. Uncertain rate changes are not silently attempted.

**Blocked by:** 02 — Deliver core power control and readback.

**Status:** ready-for-agent

- [ ] The baud command, index mapping, and device-side transition are verified on the target unit.
- [ ] The host serial port is switched and resynchronized using a documented, bounded sequence with explicit failure reporting.
- [ ] Tests cover the confirmed command and recovery/error paths without requiring hardware.
- [ ] If reliable device and host synchronization cannot be verified, the public baud-changing operation is omitted and the limitation is documented.
