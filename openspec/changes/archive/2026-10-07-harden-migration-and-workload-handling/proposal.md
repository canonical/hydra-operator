## Why

Reviewing the fix for #564 surfaced problems around it. A pending schema
upgrade looked like any other wait, `run-migration` failed without saying why,
secrets could reach the logs, a database password with special characters
broke Hydra, and a stopped workload could stay stopped while the unit reported
active.

## What Changes

- The migration status reflects the database. **BREAKING**: after a refresh
  that brings schema migrations, the application shows `blocked` and names
  the `run-migration` action, where it used to show `waiting`.
- Non-leader units say they wait for the leader.
- `run-migration` reports why it failed and refuses to record an unknown
  workload version.
- An older workload no longer adopts a newer schema through a new database
  integration.
- OAuth client secrets and the database password stay out of the logs, and
  logged error output is bounded.
- Database credentials containing reserved characters work.
- A stopped workload is started again, and "Failed to start the service" is
  reported only when the workload is expected to run.
- Migrations use `hydra migrate sql up`, replacing a deprecated command.

## Capabilities

### New Capabilities

- `database-migration`: how the charm migrates the Hydra database schema,
  reports the migration state and guards a schema against an older workload.
- `database-connection`: which database credentials the charm accepts.
- `workload-service`: when the charm runs Hydra and how it reports a workload
  that does not start.
- `sensitive-data-protection`: which secrets must never reach logs or action
  results.

### Modified Capabilities

None. These are the first specs of this repository.

## Non-goals

- Storing the migration state: it is read from the database each time.
- Remembering a failed automatic migration: it is retried on later events.
- Reporting a rollback as `blocked`: one unit cannot tell it from a rolling
  upgrade.
- Detecting a database encrypted with another deployment's system secret.

## Success Metrics

- `juju status` alone tells an operator whether `run-migration` is needed.
- No client secret or database password appears in `juju debug-log` in the
  tested failure paths.
- Re-adding the database integration returns to `active` without an action
  and keeps the signing keys.

## Impact

- Code: `src/charm.py`, `src/cli.py`, `src/services.py`,
  `src/integrations.py`, `src/constants.py`.
- Tests: `tests/unit/`, `tests/integration/test_charm.py`,
  `tests/integration/test_upgrade.py`.
- Operators: automation waiting for `waiting` after a refresh must also
  accept `blocked`.
- No change to charm configuration, relation data or peer data layout.
