# Testing Strategy

## 1. Unit Tests (`tests/unit`)

### A. Charm Logic Tests (`test_charm.py`)
These tests verify event handling and state transitions of the main Charm class.
**Framework**: `ops.testing` (Scenario) is the **ONLY** allowed framework.
**DEPRECATED**: `ops.testing.Harness`. Do not generate new tests using Harness.

#### Guidelines
- **State-Based**: Tests must define input `State` (relations, config, container) and assert output `State`.
- **Mocking Strategy**:
  - Mock **external** interactions (S3, Network, K8s API) in Layer 3.
  - **DO NOT** mock the Charm object itself or the `ops` framework internals.
  - Use `unittest.mock` for side effects in Layer 2 but prefer `State` manipulation for Layer 1.
- **Structure (AAA)**:
  - **Arrange**: Setup `Context` and input `State`.
  - **Act**: `ctx.run(event, state)`.
  - **Assert**: Check `out.unit_status`, `out.relation_data`, `out.scriptexecutions`.

### B. Component/Helper Tests (`test_services.py`, `test_cli.py`, etc.)
These tests verify isolated logic in helper classes, services, or data structures.
**Framework**: `pytest` + `unittest.mock`.

#### Guidelines
- **Isolation**: Test the class/function in isolation. Do not instantiate the Charm or use Scenario/Harness.
- **Mocking Strategy**:
  - Mock `ops` primitives (`Container`, `Model`, `Secret`) directly using `MagicMock`.
  - **Context Managers**: When mocking method that return context managers (like `container.pull`), ensure the mock implements the context manager protocol (`__enter__`).
- **Performance**: These tests should be extremely fast and avoid the overhead of the Juju event loop.


## 2. Integration Tests (`tests/integration`)
**Framework**: `jubilant`.

### Guidelines
- Focus on real infrastructure interaction.
- Use `jubilant` fixtures for Juju model interaction.
- Verify real outcomes (e.g., "Is the service actually reachable over HTTP?") rather than internal state names.
- Use `pytest` features (fixtures, parametrization) to reduce code duplication.
