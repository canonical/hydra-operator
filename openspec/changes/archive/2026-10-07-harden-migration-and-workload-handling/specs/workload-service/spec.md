## ADDED Requirements

### Requirement: Workload runs when its requirements are met

The charm SHALL keep Hydra running whenever everything it needs is in place:
the database, the public ingress, the login UI, the secrets and a recorded
schema migration.

#### Scenario: Stopped workload with an unchanged configuration

- **WHEN** Hydra is stopped, its requirements are met and its configuration
  has not changed
- **THEN** the charm SHALL start Hydra on the next event

#### Scenario: Running workload with an unchanged configuration

- **WHEN** Hydra is running and nothing in its configuration has changed
- **THEN** the charm SHALL NOT restart it

#### Scenario: Workload keeps crashing

- **WHEN** Hydra exits repeatedly and Pebble is restarting it with a backoff
- **THEN** the charm SHALL leave the restarts to Pebble and SHALL NOT restart
  Hydra on each event

### Requirement: Start failures are reported accurately

The unit SHALL show "Failed to start the service" only when the charm expects
Hydra to run and it does not.

#### Scenario: Workload fails to start

- **WHEN** the requirements of Hydra are met and Hydra cannot be started
- **THEN** the unit SHALL show `blocked` with the message
  "Failed to start the service, please check the hydra container logs"
- **AND** it SHALL show that status at the end of the event in which the
  start failed

#### Scenario: Workload exits right after starting

- **WHEN** the requirements of Hydra are met, Hydra is not running and its
  readiness check is failing
- **THEN** the unit SHALL show `blocked` with the same message, whatever the
  workload container reports as the state of the stopped service

#### Scenario: Charm keeps the workload stopped

- **WHEN** the charm has stopped Hydra, or has not started it, because a
  requirement is missing or a migration is pending
- **THEN** the unit SHALL show the status of what is missing
- **AND** it SHALL NOT show "Failed to start the service"

### Requirement: Unavailable workload container does not fail events

The charm SHALL treat a workload container that cannot be reached as a
temporary condition while it reads the workload version, checks or migrates
the database schema, and configures or starts Hydra.

#### Scenario: Container goes away during an event

- **WHEN** the workload container cannot be reached during one of those
  steps, including in the middle of a command
- **THEN** the event SHALL complete without an error
- **AND** the charm SHALL do the remaining work on a later event

### Requirement: Incomplete optional integrations do not disrupt the workload

The charm SHALL ignore an optional integration that has not provided its data
yet.

#### Scenario: Tracing integration without an endpoint

- **WHEN** the tracing integration is ready but has not published the endpoint
  that Hydra uses
- **THEN** Hydra SHALL keep running without tracing
- **AND** Hydra SHALL NOT be given an empty tracing endpoint

#### Scenario: Token hook integration without data

- **WHEN** the token hook integration is ready but has provided no data
- **THEN** Hydra SHALL keep running without a token hook
