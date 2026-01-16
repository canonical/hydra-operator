# Syntax & Typing

## Python Version
- Target Python 3.10+ syntax.

## Type Guarding
- **Strict Typing**: All function signatures must be fully typed.
- **Modern Syntax**:
  - Use `str | None` instead of `Optional[str]`.
  - Use `list[str]` instead of `List[str]`.
  - Use `dict[str, Any]` instead of `Dict[str, Any]`.
  - **PROHIBITED**: `typing.Optional`, `typing.List`, `typing.Dict`, `typing.Union`.

## Data Passing
- **Boundaries**: Data crossing layer boundaries (especially Relation Data logic) **MUST** use strictly typed structures.
- **Tooling**:
  - Use **Pydantic** (`pydantic.BaseModel`) for robust validation, especially for external inputs (config, relation data).
  - Use `dataclasses.dataclass(frozen=True)` for internal immutable data structures.
- **Prohibited**: Passing raw `dict` objects between layers or logical components. Always convert to a model first.

## Docstrings
- Use Google-style docstrings.
- Mandatory for all public methods and classes.
