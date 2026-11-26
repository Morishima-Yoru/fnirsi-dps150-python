# 02: Deliver core power control and readback

**What to build:** A caller can set voltage/current, explicitly enable or disable the output, and synchronously request current values and device status. Results use typed dataclasses. No background monitor or polling loop is introduced.

**Blocked by:** 01 — Establish the installable serial-session foundation.

**Status:** completed

- [x] Voltage and current setters accept finite floats in V and A and reject invalid or verified out-of-range values without clamping; comparisons use the encoded float32 value.
- [x] Setpoint writes do not issue output-control commands. COM64 readbacks stayed OFF during setpoint write/restore verification; changing output is a separate explicit API call.
- [x] Explicit read methods return measurements and status in documented dataclasses.
- [x] Read and control behavior is exercised with fake-serial tests; default tests never access hardware or enable its output.
- [x] The separate manual output-ON helper requires an environment opt-in, exact no-load confirmation, caller-supplied voltage/current ceilings, checks command/state readback only, and attempts output OFF in `finally`. On COM64, with no load and unchanged `12.0 V` / `5.0 A` setpoints used as the `12 V` / `5 A` ceilings, the output ON and OFF states both matched status readback; a follow-up read confirmed output OFF and unchanged setpoints. No load behavior or 100 W capability was tested.
- [x] Documentation does not claim loaded regulation or current-delivery validation from a no-load test.

**Verification:** 29 offline unit tests, flake8, and `uv build` passed. On the target COM64 unit, status and measurements were read; with output OFF, setpoints were written to `0.0 V`/`0.0 A`, read back, and restored to `12.0 V`/`5.0 A`; output remained OFF. A separately gated no-load test then verified `SET type 219` ON and OFF command/state readbacks using `12 V` / `5 A` ceilings; final status confirmed output OFF and setpoints unchanged. No buzzer/volume fields were queried or changed during this output-control test. This does not validate loaded regulation, current delivery, 100 W capability, or use as an emergency shutdown.
