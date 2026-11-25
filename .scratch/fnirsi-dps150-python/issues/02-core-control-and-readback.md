# 02: Deliver core power control and readback

**What to build:** A caller can set voltage/current, explicitly enable or disable the output, and synchronously request current values and device status. Results use typed dataclasses. No background monitor or polling loop is introduced.

**Blocked by:** 01 — Establish the installable serial-session foundation.

**Status:** ready-for-agent

- [ ] Voltage and current setters accept finite floats in V and A and reject invalid or verified out-of-range values without clamping.
- [ ] Setpoint writes do not enable the output; only an explicit output-control call changes output state.
- [ ] Explicit read methods return measurements and status in documented dataclasses.
- [ ] Read and control behavior is exercised with fake-serial tests; default tests never turn output on.
- [ ] Any hardware test that enables output is a separate manual opt-in, assumes no load, requires explicit confirmation and caller-supplied voltage/current ceilings, checks command/state readback only, and attempts to turn output off afterward.
- [ ] The documentation does not claim loaded regulation or current-delivery validation from a no-load test.
