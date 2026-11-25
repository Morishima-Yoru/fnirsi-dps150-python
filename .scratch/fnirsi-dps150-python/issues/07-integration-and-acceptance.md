# 07: Integrate capability slices and verify acceptance

**What to build:** The completed capabilities work together as one installable library with consistent public behavior, documentation, and offline tests. Unverified device behavior remains clearly unsupported rather than being inferred from a reference implementation.

**Blocked by:** 03 — Add verified OVP/OCP controls; 04 — Support native preset operations when available; 05 — Add verified non-baud system settings; 06 — Safely change baud rate and resynchronize.

**Status:** ready-for-agent

- [ ] All completed feature slices are integrated without duplicating or changing the shared serial/protocol foundation inconsistently.
- [ ] The package installs and its automated, hardware-free tests pass on the minimum supported Python version.
- [ ] Public documentation matches implemented behavior and separates target-device verification from reverse-engineered observations.
- [ ] Unsupported protections, presets, settings, or baud operations fail explicitly and are documented as such.
- [ ] No default test enables output; the manual no-load output check retains its explicit confirmation, caller-provided limits, state readback, and shutdown safeguards.
- [ ] The integration branch is ready for a user review before any release or PyPI publication.
