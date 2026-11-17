# sensitive-data-protection Specification

## Purpose

Define which secrets the charm keeps out of its logs, unit statuses and
action results. Logs are widely readable and are forwarded to other systems,
so a secret written there is exposed.

## Requirements

### Requirement: OAuth client secrets are not logged

The charm SHALL NOT write the secret of an OAuth client to its logs.

#### Scenario: Client is created or updated

- **WHEN** the charm creates or updates an OAuth client that has a secret
- **THEN** the log line that records the command SHALL show a placeholder in
  place of the secret

#### Scenario: Client command fails

- **WHEN** the command that creates or updates an OAuth client fails
- **THEN** the logged error SHALL NOT contain the secret

### Requirement: Database password is not exposed

The charm SHALL NOT write the database password to its logs, to a unit status
or to an action result.

#### Scenario: Hydra prints its connection settings

- **WHEN** a migration command fails and Hydra prints the database connection
  string it was given
- **THEN** the password SHALL be replaced by a placeholder in the logged error
  and in the failure message of the `run-migration` action

#### Scenario: Output is cut inside the connection string

- **WHEN** the output that carries the connection string is longer than the
  bound on logged output
- **THEN** no part of the password SHALL appear in the shortened output

#### Scenario: Output mentions an ordinary address

- **WHEN** the output of a command contains an address that is not a database
  connection string
- **THEN** that address SHALL be logged unchanged

### Requirement: Workload output is not copied into start errors

The charm SHALL NOT copy what Hydra printed into the error it logs when Hydra
cannot be started or stopped. Hydra prints the values it rejects, which can be
secrets.

#### Scenario: Hydra rejects a secret at start

- **WHEN** Hydra exits at start because a secret in its configuration is
  invalid, and prints that secret
- **THEN** the error logged by the charm SHALL say that the service failed to
  start
- **AND** it SHALL NOT contain the secret

### Requirement: Logged error output is bounded

The charm SHALL bound the output of a failed command that it logs or returns.

#### Scenario: Hydra follows its error with a long trace

- **WHEN** a command fails and Hydra prints its error followed by a trace of
  several kilobytes
- **THEN** the logged output SHALL keep the error and be cut after a fixed
  length
- **AND** the failure message of the `run-migration` action SHALL start with
  the error and be at most a few hundred characters long

