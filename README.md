# FNIRSI DPS150 Python Library

A small, synchronous Python library for controlling the FNIRSI DPS150 over USB virtual serial. This repository is at the specification stage; implementation is tracked as local, independently actionable tickets.

## Project documents

- [Library specification](DPS150-LIBRARY-SPEC.md)
- [Protocol research and source comparison](DPS150-PROTOCOL.md)
- [Agent and coding instructions](AGENTS.md)
- Tickets: `.scratch/fnirsi-dps150-python/issues/`

Protocol details are reverse-engineered and not an official FNIRSI specification. Device-specific behavior must be verified before claiming support.

## Development setup

Use CPython 3.10 or newer and `uv`. The checked-in `.python-version` selects Python 3.10 for minimum-version checks. The implementation ticket that introduces package metadata will define the dependency sync and test commands; no virtual environment or runtime dependencies are needed for this documents-only bootstrap.

## Worktree order

Use this clone as the integration checkout. Implement tickets 01 and 02 sequentially. Once ticket 02 is integrated, tickets 03–06 can use separate Git worktrees based on the same updated integration commit; keep their changes within their capability and tests, and do not independently modify the shared serial transport. Integrate all four slices before ticket 07.

For example, create the first isolated checkout from the bootstrap branch:

```powershell
git worktree add ..\dps150-ticket-01 -b feat/01-serial-session docs/workspace-bootstrap
```

For later tickets, use the integration branch containing tickets 01 and 02 as the base. Keep each worktree on its own branch; do not run concurrent work in the same checkout.
