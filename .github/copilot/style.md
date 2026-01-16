# Style, Syntax & Typing

## Python Version
- Target **Python 3.12** features and syntax.

## Typing Constraints
- **Universal Strictness**: All function signatures must be fully typed.
- **No Legacy Imports**:
  - ✅ Use `str | None` (NOT `Optional[str]`)
  - ✅ Use `list[str]` (NOT `List[str]`)
  - ✅ Use `dict[str, Any]` (NOT `Dict[str, Any]`)
  - **PROHIBITED**: `typing.List`, `typing.Dict`, `typing.Optional`, `typing.Union`.
- **Any**: Avoid `Any`. If used, it must be justified with a comment.

## Data Safety
- **Boundaries**: Data crossing from Layer 2 to Layer 1 MUST use Pydantic Models or Frozen Dataclasses.
- **No Raw Dicts**: Do not pass raw dictionaries as internal data structures. validate them into objects immediately.

## Refactoring Rules
- **Surgical Changes**: Modify only necessary lines.
- **No Duplication**: Check for existing helper methods in `utils.py` or libraries before writing new ones.
