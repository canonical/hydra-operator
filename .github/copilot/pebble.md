# Pebble & Container Management

## Abstraction
We do not interact with the `ops.model.Container` object directly in the charm code for complex operations.

- **PebbleService / WorkloadService**: All container interactions (exec, push, pull, layer planning) MUST be encapsulated in a service class in `src/services.py`.
- **Reasoning**: This allows for easier mocking in Unit tests and separation of "what we want to do" from "how we talk to the socket".

## Layer Management
- **Plan, Don't Patch**: Construct complete Pebble layers in Python code rather than patching existing ones where possible.
- **EAFP**: When connecting to the container, assume it might not be ready. Catch `ops.pebble.ConnectionError` and set `WaitingStatus` gracefully.

## Container-Ready Events
- The `pebble_ready` event is the earliest point we can interact with the workload.
- **Guard Clauses**: Check `if not container.can_connect():` at the start of event handlers requiring workload access. return `WaitingStatus("Waiting for pebble")`.
