## ADDED Requirements

### Requirement: Fresh database is migrated automatically

The charm SHALL migrate a database that holds no Hydra schema without operator
action, and SHALL start the workload only once the migration is recorded.

#### Scenario: First integration with an empty database

- **WHEN** the database integration provides an empty database and everything
  else the workload needs is in place
- **THEN** the leader unit SHALL apply the schema migrations
- **AND** the application SHALL reach `active` without an operator action

#### Scenario: Automatic migration fails before changing the database

- **WHEN** the automatic migration fails and the database is still empty
- **THEN** the workload SHALL NOT be started
- **AND** the leader unit SHALL show `waiting` with the message
  "Waiting for database migration"
- **AND** the migration SHALL be attempted again on a later event, at most
  once per event

#### Scenario: Automatic migration stops part-way

- **WHEN** the automatic migration fails after applying some migrations
- **THEN** the charm SHALL NOT attempt the migration again by itself
- **AND** the leader unit SHALL show `blocked` and ask for the `run-migration`
  action

### Requirement: Schema upgrades require the run-migration action

The charm SHALL NOT apply migrations to a database that already holds a Hydra
schema unless the operator runs the `run-migration` action on the leader unit.

**BREAKING**: while a schema upgrade is pending, the leader unit shows
`blocked`. It used to show `waiting`.

#### Scenario: Refresh brings new schema migrations

- **WHEN** the workload is refreshed to a version with schema migrations that
  the database does not have
- **THEN** the leader unit SHALL show `blocked` with the message
  "Database schema upgrade is pending, run the `run-migration` action"
- **AND** the workload SHALL NOT be started against that database

#### Scenario: Refresh brings no schema migrations

- **WHEN** the workload is refreshed to a version whose schema the database
  already has
- **THEN** the application SHALL reach `active` without an operator action

#### Scenario: Operator runs the migration

- **WHEN** the operator runs `run-migration` on the leader unit while a schema
  upgrade is pending, and the action succeeds
- **THEN** the application SHALL reach `active`

### Requirement: Migration status is read from the database

The charm SHALL derive the migration status from the state of the database at
the time of the event. It SHALL NOT keep that state between events.

#### Scenario: Unit is not the leader

- **WHEN** the migration is not recorded yet and the unit is not the leader
- **THEN** the unit SHALL show `waiting` with the message
  "Waiting for leader unit to run the migration"
- **AND** the unit SHALL NOT query the database for the schema state

#### Scenario: Schema state cannot be read

- **WHEN** the leader unit cannot read the schema state, for example because
  the database is unreachable
- **THEN** the leader unit SHALL show `waiting` with the message
  "Waiting for database migration"
- **AND** nothing SHALL be migrated or recorded
- **AND** the schema state SHALL be read again on a later event

#### Scenario: Workload version is unknown

- **WHEN** the charm cannot read the version of the workload
- **THEN** the unit SHALL show `waiting` with the message
  "Waiting for the workload version"
- **AND** nothing SHALL be migrated or recorded

#### Scenario: Something else holds the unit back

- **WHEN** the migration is not recorded yet and another requirement of the
  workload is missing, such as the public ingress
- **THEN** the leader unit SHALL NOT query the database for the schema state

#### Scenario: Event that reconciles nothing

- **WHEN** a schema upgrade is pending and the leader unit handles an event
  that changes nothing, such as an unrelated action
- **THEN** the leader unit SHALL still show `blocked` with the message asking
  for the `run-migration` action

### Requirement: Older workload does not adopt a newer schema

The charm SHALL NOT record a migration by itself when the database was last
migrated by a workload version newer than the one that is running. An older
workload cannot see the newer migrations, so to it the schema looks complete.

#### Scenario: Workload is rolled back

- **WHEN** the workload is refreshed to a version older than the one that
  last migrated the database of the current integration
- **THEN** the workload SHALL NOT be started
- **AND** the leader unit SHALL show `waiting` with the message
  "Database schema is newer than the workload, run the `run-migration` action
  if this is a rollback"

#### Scenario: New integration with the database of an earlier integration

- **WHEN** a new database integration provides a database that already holds
  a complete schema, and the most recent earlier integration recorded a
  workload version newer than the one that is running
- **THEN** the charm SHALL NOT record the migration by itself
- **AND** the leader unit SHALL show the same `waiting` message as for a
  rollback

#### Scenario: New integration with an empty database

- **WHEN** a new database integration provides an empty database
- **THEN** the leader unit SHALL migrate it, whatever versions earlier
  integrations recorded

#### Scenario: Earlier rollback was resolved

- **WHEN** a new database integration provides a database that already holds
  a complete schema, and the most recent earlier integration recorded the
  version that is running, although an older integration recorded a newer one
- **THEN** the application SHALL reach `active` without an operator action

#### Scenario: Current integration has its own record

- **WHEN** the current integration has a migration record that is not newer
  than the workload
- **THEN** the records of earlier integrations SHALL NOT hold the unit back

### Requirement: run-migration reports its outcome

The `run-migration` action SHALL say why it failed, and SHALL NOT leave a
record that passes for a finished migration when it did not finish.

#### Scenario: Hydra rejects the migration

- **WHEN** the migration command exits with an error
- **THEN** the action SHALL fail with a message that contains the error Hydra
  reported

#### Scenario: Database cannot be reached

- **WHEN** the migration command does not finish before the action timeout
- **THEN** the action SHALL fail with a message that contains the last
  connection error Hydra reported

#### Scenario: Workload version is unknown

- **WHEN** the charm cannot read the version of the workload
- **THEN** the action SHALL fail before migrating
- **AND** no migration SHALL be recorded
