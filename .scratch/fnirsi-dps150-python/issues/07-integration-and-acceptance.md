# 07: Integrate capability slices and verify acceptance

**What to build:** The supported capabilities work together as one installable library with consistent public behavior, documentation, and offline tests. Unverified device behavior remains clearly unsupported rather than being inferred from a reference implementation.

**Blocked by:** 03 — Add verified protection controls (OPP/OTP/LVP supported; OVP/OCP excluded); 04 — Support native preset operations when available; 05 — Add verified non-baud system settings; 06 — Safely change baud rate and resynchronize.

**Status:** complete — verified non-excluded capabilities integrated

- [x] Original tickets #03–#06 were integrated from four independent worktrees sharing the same #02 baseline. This follow-up adds only serial-read exception normalization to the shared transport and reuses that seam for the new capabilities.
- [x] The package builds and its hardware-free tests pass on CPython 3.10.20.
- [x] README, library spec, protocol evidence, and ticket outcomes distinguish target observations from unverified reverse-engineered behavior.
- [x] Verified preset slot read/write and brightness/metering operations are exposed through typed high-level methods; writes require output OFF and preset writes do not load active setpoints.
- [x] Added typed target-backed input-voltage, temperature, regulation-mode, device-info, and OPP/OTP/LVP reads; OPP/OTP/LVP reversible writes require output OFF and do not test trips.
- [x] OVP/OCP and buzzer/volume remain excluded. Native preset loading, capacity/energy semantics or writes, and baud changes remain unsupported due missing evidence.
- [x] Serial read failures are normalized to `DPS150CommunicationError` with their original cause preserved.
- [x] Default tests use fake serial only. The separate output-ON helper requires environment opt-in, exact no-load confirmation, and caller V/A ceilings; it temporarily caps setpoints, verifies only command/state readback, attempts OFF in `finally`, and restores originals only after OFF is confirmed. COM64 passed with 1.0 V / 0.1 A ceilings and restored `12.0 V` / `5.0 A`; final readback was OFF. No load behavior or 100 W capability was tested.
- [x] The integration branch is ready for review; no release or PyPI publication was attempted.

**Verification:** `uv run python -m unittest discover -s tests -v` — 51 passed; `uv run flake8 src tests` — passed; `uv build` — source distribution and wheel built. COM64 verified input voltage, temperature, regulation mode, device identity, reversible OPP/OTP/LVP GET/SET, preset slots, brightness/metering, and the bounded no-load output command/state check. All modified values and setpoints were restored; final output was OFF. No protection trip, native preset load, baud change, capacity/energy write, or buzzer/volume type-215 command was tested.
