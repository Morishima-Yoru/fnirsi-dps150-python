# 07: Integrate capability slices and verify acceptance

**What to build:** The completed capabilities work together as one installable library with consistent public behavior, documentation, and offline tests. Unverified device behavior remains clearly unsupported rather than being inferred from a reference implementation.

**Blocked by:** 03 — Add verified OVP/OCP controls; 04 — Support native preset operations when available; 05 — Add verified non-baud system settings; 06 — Safely change baud rate and resynchronize.

**Status:** complete — ready for user review

- [x] Tickets #03–#06 are integrated from four independent worktrees sharing the same #02 baseline; no slice changed the shared serial/protocol transport.
- [x] The package builds and its hardware-free tests pass on CPython 3.10.20.
- [x] README, library spec, protocol evidence, and ticket outcomes distinguish target observations from unverified reverse-engineered behavior.
- [x] Unverified protection, preset, system-setting, and baud operations are not exposed; attempts to call absent methods fail with `AttributeError` rather than a success-shaped stub.
- [x] Default tests use fake serial only. The separate output-ON helper retains environment opt-in, exact no-load confirmation, caller V/A ceilings, state readback, and `finally` shutdown attempt; it was not run.
- [x] The integration branch is ready for review; no release or PyPI publication was attempted.

**Verification:** `uv run python -m unittest discover -s tests -v` — 28 passed; `uv run flake8 src tests` — passed; `uv build` — source distribution and wheel built. COM64 status/readback and GET-only type scan were recorded; setpoints were safely restored with output OFF. No output-ON or unsupported-feature SET command was sent.
