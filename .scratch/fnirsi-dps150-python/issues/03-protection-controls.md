# 03: Add verified protection controls

**What to build:** Expose only protection settings whose target behavior is verified. OVP/OCP are excluded from the current support scope; OPP/OTP/LVP are included when safe read/write behavior is proven.

**Blocked by:** 02 — Deliver core power control and readback.

**Status:** partial — OPP/OTP/LVP verified; OVP/OCP excluded

- [x] COM64 GET types 211–213 returned four-byte float32 values for OPP/OTP/LVP: `150.0 W`, `80.0 °C`, and `5.0 V`.
- [x] With output OFF, temporarily wrote `149.5 W`, `79.5 °C`, and `5.1 V`; each value read back, and all original values were restored exactly. Output remained OFF and active setpoints remained `12.0 V` / `5.0 A`.
- [x] Added typed `ProtectionSettings`, `get_protection_settings()`, and output-OFF-guarded `set_protection_settings()` for OPP/OTP/LVP. The three writes are non-atomic; supported numeric ranges are not independently known.
- [ ] OPP/OTP/LVP trip behavior is verified. **Not tested:** no protection trigger was attempted.
- [ ] OVP/OCP meanings and SET semantics are verified. **Unverified and excluded:** references conflict between one-byte flags and float32 thresholds; no OVP/OCP control API is exposed.
- [x] Hardware-free tests cover supported field reads/writes, output-OFF guard, and invalid values. Default tests never enable output.

**Evidence limit:** The reversible target test confirms only OPP/OTP/LVP setting readback and restoration. It does not confirm protection trips, cross-firmware behavior, or valid threshold ranges. OVP/OCP remain outside scope.
