# Python Coding Style

## Project Scope
- This repository is a small Python hardware-control library, not a GUI application or service.
- Prefer the smallest package structure that satisfies the library specification. Do not add GUI/FSM/controller layers, YAML configuration, singletons, Rich, daily log rotation, or an `AppLogger` wrapper unless a concrete library requirement justifies them.
- Use the standard library and pySerial; add runtime dependencies only when the specification requires them.
- Keep serial transport and packet details private behind the high-level `DPS150` interface. Hardware access must remain opt-in in tests, as specified in `DPS150-LIBRARY-SPEC.md`.
- Apply the architecture and logging suggestions below only when they fit this library's scope; they do not require creating application infrastructure.

## Language and Tooling
- Use CPython `>=3.10` for library compatibility. Development tools may use a newer version.
- Use `uv` to manage Python environments.
- Avoid `typing.Any` in type hints; prefer `object` or generics, except in low-level C-FFI/DLL wrapper modules.
- Use Google-style docstrings for classes and methods.
  - Include `Args:`, `Returns:`, and `Raises:` sections when appropriate.
  - Use ``:class:`Foo``` to reference other classes in docstrings.
  - Include an `Attributes:` section for class attributes.
- Use standard 4-space indentation (PEP 8).
- Keep code clearly type-hinted and flake8-compliant; run the checker with `uv`.

## Naming Conventions
- Variables and functions: descriptive `snake_case`; use explicit verbs for functions.
- Classes and exceptions: noun-based `PascalCase` names.
- Constants and `Final` values: `UPPER_CASE`; explicitly annotate them with `Final[...]`.
- Private class members: `_snake_case` with one leading underscore.
- Name-mangled lifecycle methods: `__snake_case` with two leading underscores, used for bootstrapping routines (for example, `__construct_gui`).
- Generic type variables: suffix with `T` (for example, `StateT`, `PossibleBackendT`). Use `TypeVar` and `Generic` rather than PEP 695 syntax so runtime code remains compatible with Python 3.10.

## Type Hints
- Use `A | B` instead of `Union[A, B]`.
- Use `A | None` instead of `Optional[A]`.
- Use built-in generic collections (`list[str]`, `dict[str, int]`) instead of `List` or `Dict` from `typing`.
- For explicit generic aliases, use `TypeAlias` from `typing` with a Python 3.10-compatible type variable:
  ```python
  from types import EllipsisType
  from typing import TypeAlias, TypeVar

  ValueT = TypeVar("ValueT")
  _OrEllipsis: TypeAlias = ValueT | EllipsisType
  ```

## Architecture
- Organize code into clean, decoupled module layers:
  - `definitions/`: interfaces, exceptions, namespace enums, and type aliases.
  - `backends/`: low-level communication drivers (FTD2XX, VCP, SCPI).
  - `implements/`: concrete hardware/device implementors.
  - `controllers/`: sub-controllers (ISN, Menu, Status, MainController).
  - `managers/`: system managers (Config, Logger, Passphrase, Session).
  - `tasks/`: FSM task step handlers.
  - `services/`: external service integration (SFIS, Web APIs).
  - `view/`: GUI views and popups.
  - `core/`: bootstrap lifecycle, AppRuntime, and engine cores.
- Apply these patterns where appropriate:
  - **Abstract Factory** to decouple board models from communication backends.
  - **FSM Orchestration** with Moore/Mealy state machines and picklable `FsmSnapshot`.
  - **Controller Orchestration (MVC/PAC)** with `MainController` composing sub-controllers.
  - **Hardware Strategy/Backend Abstraction** by injecting `CommunicationInterface`.
  - **Application Lifecycle Bootstrapper** through `AppRuntime.bootstrap()` with `atexit` cleanup.

## Exception Handling
- Never swallow exceptions silently; log errors before re-raising.
- Place custom exception classes in `definitions/exceptions.py`.
- Define one root exception per project (for example, `HiokiError` or `FsmError`), then subclass it for specific domains.
- Preserve the original traceback with `raise NewException(...) from err`.
- Use `contextlib.suppress(Exception)` only for explicit safe cleanup paths (for example, hardware disconnect on `atexit`).

## Logging
- Use `AppLogger` as the standard logging wrapper.
- Use `rich.logging.RichHandler` for colored terminal output.
- Rotate log files daily with the `YYYY-MM-DD.log` filename format.
- Initialize module-level loggers as `_logger = logging.getLogger(__name__)`.

## Configuration
- Store user-editable settings in YAML files (`config.yaml`).
- Map YAML content to frozen dataclass models in `definitions/namespace.py`.
- Expose configuration through a `ConfigManager` singleton parsed at startup.
