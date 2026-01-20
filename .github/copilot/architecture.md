# Architecture & Logic

## Strict 3-Layer Architecture
The codebase follows a strict separation of concerns developed by the Canonical Identity Team. Dependencies flow **downwards** only.

### Layer 1: Orchestration (`src/charm.py`)
- **Scope**: Event handling, State decisions, Data routing.
- **Responsibility**: reacting to Juju events, orchestrating calls to Layer 2, maintaining Unit Status.
- **PROHIBITED**:
  - Business logic/complex calculations.
  - Direct calls to `pebble` or K8s API.
  - Direct manipulation of relation databags (use Integration wrappers).

### Layer 2: Abstraction (`src/services.py`, `src/integrations.py`, `src/secret.py`)
- **Scope**: Domain logic and interface wrappers.
- **Responsibility**:
  - `integrations.py`: Strongly-typed wrappers around Juju relations. Validates incoming data using Pydantic.
  - `services.py`: Encapsulates operations (Pebble, Workload).
  - `configs.py`: Validates charm config.

### Layer 3: Infrastructure (`ops`, `lightkube`, `pebble`)
- **Scope**: Low-level platform interaction.
- **Access**: Accessed **ONLY** via Layer 2 wrappers. Layer 1 should never import `lightkube` directly.

## Data Flow Pattern (Source -> Sink)
1.  **Source**: Data comes from Config, Relations, or Secrets.
2.  **Validation**: Data is validated immediately at the boundary (Layer 2) using **Pydantic Models**.
3.  **Coordination**: Layer 1 (Charm) receives the valid model and decides *what* to do.
4.  **Sink**: Layer 1 calls Layer 2 services to push data to Sinks (Pebble environment, Relation databags, Workload).
