# Hard Constraints (The "No-Go" List)

## 1. Type Constraints
- **NO** legacy typing module imports (`List`, `Dict`, `Optional`, `Union`) for type hints. Use built-in generics and `|` operator.
- **NO** `Any` unless absolutely unavoidable (and justified with a comment).

## 2. Refactoring Constraints
- **Surgical Changes**: When fixing bugs, modify only the necessary lines. Avoid large-scale reformatting or renaming unless requested.
- **Preserve Behavior**: Do not change public interface contracts without explicit instruction.
- **No Duplication**: Before adding a helper function, verify it (or a semantic equivalent) does not already exist.
- **Context Verification**: Read the file context immediately before applying edits to ensure patch accuracy.

## 3. Data Safety
- **NO** raw `dict` passing for complex data. Encapsulate in `pydantic` models or `dataclasses`.
- **NO** hardcoded secrets or credentials. Use Juju Secrets.

## 4. Testing
- **NO** `Harness` for new unit tests. Use `ops.testing` (Scenario).
- **NO** bare `assert` in production code.

## 5. Error Handling
- **NO** bare `except Exception:`. Catch specific exceptions (`PebbleServiceError`, `ModelError`, etc.).
- **NO** swallowing errors silently. Log them or re-raise.

## 6. Validation & Formatting
- **Mandatory Formatting**: You MUST run `tox -e fmt` to apply coding style standards after editing files.
- **Mandatory Linting**: You MUST run `tox -e lint` to verify compliance before considering a task complete.
