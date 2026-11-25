# 01: Establish the installable serial-session foundation

**What to build:** A Python caller can install the library and use `DPS150` to open and close a USB virtual serial connection, explicitly or with a context manager, and make a safe read of device status. The connection layer handles packet framing and errors internally and never changes the instrument's output state.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] The package installs on CPython 3.10+ and uses pySerial for cross-platform USB VCP access.
- [ ] Construction performs no serial I/O; explicit `open()` / `close()` and context-manager use manage the connection.
- [ ] Opening, closing, and status reads do not send commands that change output state.
- [ ] Private frame encoding/decoding validates length and checksum and handles fragmented or malformed input with explicit typed errors.
- [ ] The serial timeout is finite and configurable; communication errors preserve their cause and are not automatically retried.
- [ ] Fake-serial tests cover successful status reads, fragmented frames, malformed frames, timeout, and cleanup without hardware.
