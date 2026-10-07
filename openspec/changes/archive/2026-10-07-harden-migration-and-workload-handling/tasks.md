## 1. Migration status

- [x] 1.1 In `src/charm.py`, read the schema state through a property that is
  computed at most once per hook and never stored, and use it in
  `_reconcile_migration`. Unit tests in `tests/unit/test_charm.py`: the status
  command runs once per event; a failed check neither migrates nor records.
- [x] 1.2 In `src/charm.py`, add `_migration_status` and use it in
  `_on_collect_status`: `blocked` for a pending upgrade, and a `waiting`
  message each for the leader, a non-leader, an unknown workload version and a
  schema newer than the workload. Unit tests in `tests/unit/test_charm.py`
  cover each status, a non-leader that does not query the database, a missing
  requirement that prevents the query, and an event that reconciles nothing.
- [x] 1.3 In `src/services.py`, look the workload version up once per hook,
  also when the lookup fails. Unit tests in `tests/unit/test_services.py`
  (one lookup, known and unknown) and `tests/unit/test_charm.py` (one lookup
  per event).
- [x] 1.4 In `src/charm.py`, attempt the automatic migration at most once per
  hook and read the schema state again after a failed attempt. Unit tests in
  `tests/unit/test_charm.py`: a failure that applied nothing stays `waiting`,
  a failure part-way becomes `blocked`, and a replayed deferred event does not
  migrate again.

## 2. Rollback guard

- [x] 2.1 In `src/integrations.py`, add `PeerData.migration_versions()`, which
  returns the recorded versions by integration id, and move the key prefix to
  `src/constants.py`. Unit tests in `tests/unit/test_integrations.py`: empty
  records, non-numeric keys and unrelated keys are left out.
- [x] 2.2 In `src/charm.py`, let the record of the current integration decide
  when it exists, and otherwise the record of the most recent earlier
  integration unless the database is fresh. Unit tests in
  `tests/unit/test_charm.py`: same schema, fresh database, pending upgrade,
  unknown schema, a rollback resolved on a later integration, and an upgrade
  below a version recorded by an earlier integration.

## 3. Migration failure reporting

- [x] 3.1 In `src/cli.py`, stream the output of the migration commands and
  raise `MigrationError` with a reason that ends with what Hydra printed last.
  Unit tests in `tests/unit/test_cli.py`: exit with an error, exit after
  progress, a retry record on one and on two lines, and a bounded reason.
- [x] 3.2 In `src/charm.py`, make `run-migration` fail before migrating when
  the workload version is unknown. Unit tests in `tests/unit/test_actions.py`:
  the failure message carries the reason, and an unknown version migrates and
  records nothing.
- [x] 3.3 In `src/cli.py`, run migrations with `hydra migrate sql up -e --yes`.
  Unit tests in `tests/unit/test_cli.py` and the exec fixtures in
  `tests/unit/conftest.py`.

## 4. Sensitive data

- [x] 4.1 In `src/cli.py`, mask the value of `--secret` in the logged command.
  Unit tests in `tests/unit/test_cli.py`: creating and updating a client logs
  no secret, also when the command fails.
- [x] 4.2 In `src/cli.py`, mask the password of a URL-encoded connection string
  in logged output and in failure reasons, before the output is cut, and bound
  the logged error output. Unit tests in `tests/unit/test_cli.py`: a password
  that the bound would cut, an ordinary address left unchanged, and the bound
  itself.
- [x] 4.3 In `src/services.py`, raise the start and stop errors with the
  summary of the failed change, without the service output. Unit test in
  `tests/unit/test_services.py`: the error contains no service output and
  keeps its cause.

## 5. Database connection

- [x] 5.1 In `src/integrations.py`, percent-encode the username and password
  of the connection string. Unit test in `tests/unit/test_integrations.py`
  with reserved characters in both.

## 6. Workload service

- [x] 6.1 In `src/services.py`, make `plan()` start a service that is inactive
  after replanning, and move adding the layer and reading the config file
  inside its error handling. Unit tests in `tests/unit/test_services.py`
  (inactive is started, active and backing off are not; Pebble unreachable)
  and `tests/unit/test_charm.py` (a stopped service with an unchanged config
  is started).
- [x] 6.2 In `src/services.py`, catch Pebble errors in `get_service()` and in
  the check lookups. Unit tests in `tests/unit/test_services.py`.
- [x] 6.3 In `src/charm.py`, report "Failed to start the service" only when the
  service is expected to run, and in the hook in which the start failed. Unit
  tests in `tests/unit/test_charm.py`: a service kept stopped for a missing
  requirement, one kept stopped for a pending migration, one that should run
  and does not, and a failed plan.

## 7. Optional integrations and typing

- [x] 7.1 In `src/integrations.py`, load a tracing integration without an
  endpoint and a token hook integration without data as not ready. Unit tests
  in `tests/unit/test_integrations.py`.
- [x] 7.2 Fix the type errors mypy reports in `src/cli.py`, `src/services.py`
  and `src/integrations.py`. Covered by the existing unit tests and by mypy.

## 8. Integration tests

- [x] 8.1 In `tests/integration/test_upgrade.py`, accept a `blocked`
  application after the refresh.
- [x] 8.2 In `tests/integration/test_charm.py`, assert in
  `test_remove_integration` that the JWKS key ids are the same after the
  integration is restored.

## 9. Verification suite

- [x] 9.1 Run `tox -e fmt` and `tox -e lint`.
- [x] 9.2 Run `tox -e unit` and confirm that all tests pass.
- [x] 9.3 Run mypy on `src/` with the dependencies of the pre-commit hook.
- [x] 9.4 Break the new code on a copy of `src/`, one behaviour at a time, and
  confirm that each breakage fails at least one unit test.
- [x] 9.5 Run the changed commands against real Pebble, Hydra 26.2.0 and
  PostgreSQL 14: a password with reserved characters, a user without rights on
  the schema, an unreachable database, a stopped service, and a Hydra that
  exits at start.
- [x] 9.6 Confirm that the integration tests pass in CI.
- [x] 9.7 Run `openspec validate harden-migration-and-workload-handling
  --strict`.

## 10. Documentation & rollout

- [x] 10.1 Describe the behaviour changes in the pull request: the `blocked`
  status after a refresh with schema migrations, the new status messages, and
  `run-migration` failing on an unknown workload version.
- [x] 10.2 Add `.github/workflows/openspec-drift-detect.yaml` and
  `.agents/skills/openspec-detect-drift/SKILL.md`, so that later pull requests
  are checked against these specs.
- [ ] 10.3 Mention in the release notes that automation waiting for `waiting`
  after a refresh must also accept `blocked`.

## Implementation Notes

- The rollback guard first counted any earlier record that was newer than the
  workload. A review showed that it never switched off, so it now uses the
  most recent record only (design D2).
- "A stopped service is not failing" was first decided from the state Pebble
  reports. Older Pebble reports a crashed service the same way, so the charm
  now decides from whether it expects the service to run (design D6).
- A tracing integration without an endpoint first loaded as ready with an
  empty endpoint, which makes Hydra exit. It now loads as not ready.
- Collecting the streamed output as bytes would avoid the split-character
  limit described in the design, but `ops.testing` cannot mock an exec in
  byte mode. The text buffers were kept.
- A workload older than the schema stays `waiting` (design D2), and a failed
  automatic migration is retried instead of remembered (design D3).
