# 02: Deliver core power control and readback

**What to build:** A caller can set voltage/current, explicitly enable or disable the output, and synchronously request current values and device status. Results use typed dataclasses. No background monitor or polling loop is introduced.

**Blocked by:** 01 — Establish the installable serial-session foundation.

**Status:** completed

- [x] Voltage and current setters accept finite floats in V and A and reject invalid or verified out-of-range values without clamping; comparisons use the encoded float32 value.
- [x] Setpoint writes do not issue output-control commands. COM64 readbacks stayed OFF during setpoint write/restore verification; changing output is a separate explicit API call.
- [x] Explicit read methods return measurements and status in documented dataclasses.
- [x] COM64 target reads for input voltage (type 192) and temperature (type 196) are exposed by `get_input_voltage()` and `get_temperature()`.
- [x] COM64 `GET type 221` readback of mode value `1` is exposed as `RegulationMode.CV` by `get_regulation_mode()`; the `CC` mapping is hardware-free tested but not observed on the target.
- [x] Read and control behavior is exercised with fake-serial tests; default tests never access hardware or enable its output.
- [x] The separate manual output-ON helper requires an environment opt-in, exact no-load confirmation, and caller-supplied voltage/current ceilings. It temporarily caps setpoints while OFF, checks command/state readback only, attempts OFF in `finally`, and restores original setpoints only after OFF is confirmed. On COM64, the approved no-load test used 1.0 V / 0.1 A ceilings; ON and OFF matched status readback, then setpoints were restored to `12.0 V` / `5.0 A`. No load behavior or 100 W capability was tested.
- [x] Float32 ceiling rounding is directed downward when nearest encoding would exceed the operator's ceiling. An initial attempt safely aborted before output ON when `0.1 A` rounded slightly high; cleanup restored original setpoints, and the corrected check passed.
- [x] Documentation does not claim loaded regulation or current-delivery validation from a no-load test.

**Verification:** 51 offline unit tests, flake8, and `uv build` passed. On COM64, status and measurements were read; setpoint write/restore and output state tests preserved OFF state. The bounded no-load output test used 1.0 V / 0.1 A ceilings, verified ON/OFF state readback, and restored `12.0 V` / `5.0 A`; final status was OFF. This does not validate loaded regulation, current delivery, 100 W capability, or use as an emergency shutdown.
