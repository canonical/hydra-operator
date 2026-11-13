# OAuth client pagination and export proposal

## Why

The `list-oauth-clients` action returns only Hydra's first page of 100
clients, despite promising all clients and offering no way to continue.
Returning every client inline would risk exceeding the approximately
100 KB practical limit for Juju action results. See
[hydra-operator#674: `list-oauth-clients` action returns only the first 100 clients](https://github.com/canonical/hydra-operator/issues/674).

## What Changes

- Preserve the default single-page response of up to 100 clients and the
  existing `clients` JSON string.
- Add optional `page-size` and `page-token` inputs and return
  `next-page-token` only when another page exists. Do not add `is-last-page`.
- Add optional `export=json` to retrieve all pages and produce a complete
  JSON file that operators can retrieve with `juju scp`.
- Reject unsupported export formats and export requests that start from a
  continuation token.
- Return actionable errors rather than truncated inline results or
  successful partial exports; allow a successfully retrieved empty inventory.
- Keep OAuth client secrets out of listing and export content, and bound
  temporary export retention.
- Correct the action description to explain pagination and export. Existing
  successful listing calls remain compatible; empty inventories now succeed
  instead of failing.

## Capabilities

### New Capabilities

- `oauth-client-listing`: Backward-compatible paginated listing, continuation
  tokens, complete JSON export, safe retrieval, validation, and failure handling.

### Modified Capabilities

None. Existing sensitive-data-protection requirements remain unchanged.

## Impact

The planned implementation affects `charmcraft.yaml`, `src/cli.py`,
`src/charm.py`, supporting export/domain helpers and constants, unit tests,
integration tests, and operator documentation. It requires maintainer review
of action metadata. No database migration, new relation, or third-party
dependency is planned.

## Non-goals

- Returning all clients inline by default.
- Supporting export formats other than JSON.
- Exporting client secrets or providing an import/backup-restore interface.
- Providing a transactionally consistent snapshot during concurrent changes.
- Durable storage, cross-unit replication, or a public download endpoint.

## Success Metrics

- Existing callers retain the first-page `clients` representation without
  new inputs.
- Operators can enumerate and export more than 100 clients, including a
  previously missing client.
- Large exports are retrieved successfully without embedding their content
  in action results.
- Tests verify empty inventories, secret exclusion, validation, and
  later-page or file-write failures.
