# 07: Integrate capability slices and verify acceptance

**What to build:** The completed capabilities work together as one installable library with consistent public behavior, documentation, and offline tests. Unverified device behavior remains clearly unsupported rather than being inferred from a reference implementation.

**Blocked by:** 03 — Add verified OVP/OCP controls; 04 — Support native preset operations when available; 05 — Add verified non-baud system settings; 06 — Safely change baud rate and resynchronize.

**Status:** complete — capability expansion ready for user review

- [x] Original tickets #03–#06 were integrated from four independent worktrees sharing the same #02 baseline. This follow-up adds only serial-read exception normalization to the shared transport and reuses that seam for the new capabilities.
- [x] The package builds and its hardware-free tests pass on CPython 3.10.20.
- [x] README, library spec, protocol evidence, and ticket outcomes distinguish target observations from unverified reverse-engineered behavior.
- [x] Verified preset slot read/write and brightness/metering operations are exposed through typed high-level methods; writes require output OFF and preset writes do not load active setpoints.
- [x] OVP/OCP, native preset loading, volume/buzzer, capacity/energy writes, and baud changes remain omitted because their target behavior is unverified.
- [x] Serial read failures are normalized to `DPS150CommunicationError` with their original cause preserved.
- [x] Default tests use fake serial only. The separate output-ON helper retains environment opt-in, exact no-load confirmation, caller V/A ceilings, state readback, and `finally` shutdown attempt. Its COM64 no-load run verified ON/OFF state readbacks using unchanged `12.0 V` / `5.0 A` setpoints as ceilings; final readback was OFF. No buzzer/volume fields were queried or changed during this test. This does not validate load behavior or 100 W capability.
- [x] The integration branch is ready for review; no release or PyPI publication was attempted.

**Verification:** `uv run python -m unittest discover -s tests -v` — 40 passed; `uv run flake8 src tests` — passed; `uv build` — source distribution and wheel built. COM64 verified reversible GET/SET behavior for all six preset slots, brightness, and metering; values were restored, output remained OFF, and active setpoints stayed `12.0 V` / `5.0 A`. No OVP/OCP SET or trip, preset load, baud change, volume/buzzer query/write, or output-ON test was performed in this follow-up.
