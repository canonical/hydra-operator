# database-connection Specification

## Purpose

Define which database credentials the charm accepts from the database
integration, so that Hydra works with any username and password a database
provider hands out.

## Requirements

### Requirement: Database credentials with reserved characters

The charm SHALL connect Hydra and its migration commands to the database with
the username and password that the database integration provides, whatever
characters they contain.

#### Scenario: Password contains characters reserved in URLs

- **WHEN** the database integration provides a password that contains
  characters such as `@`, `/`, `?`, `%`, `#` or `:`
- **THEN** the workload SHALL connect to the database
- **AND** the migration commands SHALL connect to the database

#### Scenario: Username contains characters reserved in URLs

- **WHEN** the database integration provides a username that contains
  characters such as `:` or `/`
- **THEN** the workload and the migration commands SHALL connect to the
  database

#### Scenario: Credentials of letters and digits

- **WHEN** the credentials contain only letters and digits
- **THEN** the connection settings given to the workload SHALL be the same as
  before this requirement, so that a refresh does not restart the workload
  for this reason

