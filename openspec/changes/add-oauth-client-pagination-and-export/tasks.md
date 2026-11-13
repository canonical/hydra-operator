# OAuth client pagination and export tasks

## 1. Validated workload pagination

- [x] 1.1 Extend `src/cli.py` with a typed page result and explicit domain
  errors in `src/exceptions.py`; accept page size and opaque token arguments,
  validate `items` and continuation metadata, and distinguish an empty page
  from failure. Add tests in `tests/unit/test_cli.py` for valid pages, empty
  pages, absent/empty tokens, malformed JSON/models/metadata, invalid Hydra
  pagination values, and execution failure. Verify flags, response schema,
  and accepted page-size bounds against the packaged Hydra version and record
  findings in this change's `design.md`.

## 2. Shared serialization and inline result safety

- [x] 2.1 Introduce the planned domain helper `src/oauth_client_listing.py`
  and add the 90 KiB result budget to `src/constants.py`; preserve existing
  model serialization and client secret exclusion, validate user inputs,
  and measure encoded result arguments including keys and continuation
  metadata. Add `tests/unit/test_oauth_client_listing.py` for aliases,
  optional fields, secret exclusion, positive integer sizes, invalid format
  values, token/export conflicts, exact byte boundaries, JSON escaping,
  Unicode, and oversized continuation tokens. Match the actual installed
  Ops argument encoding without logging payloads.

## 3. Complete private file export

- [x] 3.1 Implement sequential page-to-file export in
  `src/oauth_client_listing.py`, with limits and paths in `src/constants.py`
  and domain failures in `src/exceptions.py`. Stream JSON using the shared
  serializer, follow tokens until exhausted, detect token cycles, enforce a
  five-minute deadline and 100 MiB file limit, and publish the completed file
  atomically in the charm container. Keep only the latest completed file,
  preserve it on pre-publication failure, use private permissions, and clean
  abandoned temporary files. Add tests in
  `tests/unit/test_oauth_client_listing.py` using a temporary directory and
  mocked page fetches for 0, 100, 101, and multiple full pages; short or empty
  pages with continuation; multi-step token cycles; later-page failure;
  timeout; write/close/replace failure; boundary-sized exports; permissions;
  atomic replacement; and cleanup without deleting the previous export.

## 4. Action contract and orchestration

- [x] 4.1 Update only `list-oauth-clients` in `charmcraft.yaml`, after
  maintainer validation, to expose optional `page-size`, `page-token`, and
  string `export` with only `json` supported. Correct its description and
  document omission semantics without introducing a default export value.
  Wire the listing/export domain helper into the action handler in
  `src/charm.py` as part of the same task, and extend
  `tests/unit/test_actions.py` to verify metadata defaults and parameter
  validation alongside handler behavior. Preserve the `clients` JSON string
  in normal mode, omit
  absent continuation tokens, return no completion flag, and return only
  export location/count metadata in export mode. Map domain and result
  transport failures to actionable action errors. Add Scenario coverage in
  `tests/unit/test_actions.py` for unchanged default calls, pagination,
  empty inventory, readiness, invalid input without I/O, inline size errors,
  `set_results` transport errors, export metadata, and secret-free failures.

## 5. End-to-end regression coverage

- [x] 5.1 Extend `tests/integration/test_charm.py` and scoped setup/cleanup
  in `tests/integration/conftest.py` to register more than 100 clients, verify
  the default remains one page, enumerate all pages using returned tokens,
  confirm a client missing from the first page is present later, and verify
  last-page omission and unchanged JSON field representation. Ensure test
  clients are removed without interfering with existing fixtures. In the
  same task, reuse that scoped setup/cleanup in
  `tests/integration/conftest.py` and extend
  `tests/integration/test_charm.py` with complete JSON export
  and actual `juju scp --container charm` retrieval using the returned unit
  and path on Juju 3.6. Use an export larger than the inline result budget;
  validate JSON, IDs, count, secret exclusion, metadata-only action results,
  and latest-only replacement. Extend `tests/integration/test_upgrade.py`
  to confirm a default listing still works after charm refresh, and new
  pagination/export inputs work on the refreshed revision.

## 6. Verification Suite

- [x] 6.1 Run `tox -e lint,unit` for changes to `src/`, `charmcraft.yaml`,
  and unit tests; run `pre-commit run mypy --all-files` for type verification
  and Markdown checks on the changed documentation. Fix only introduced
  issues and record command results in this change's `tasks.md`.
- [x] 6.2 Build the changed `charmcraft.yaml` and source with
  `charmcraft pack`, then run `tox -e integration` with the built charm on
  the supported Juju/Kubernetes stack. Record packaged Hydra version,
  file-transfer success, and any environment blockers in this `tasks.md`;
  do not mark unavailable integration verification complete.
- [x] 6.3 Run `openspec validate add-oauth-client-pagination-and-export
  --strict` and `openspec validate --all --strict`. Check implementation
  against this change's `specs/oauth-client-listing/spec.md`, and record
  intentional deviations in `tasks.md` before final review.

## 7. Documentation & Rollout

- [x] 7.1 Update `README.md` with action examples for default listing,
  continuation tokens, `export=json`, and retrieval using the returned unit
  and container. Document the practical inline budget, 100 MiB export limit,
  five-minute export deadline, latest-only temporary retention, empty-list
  success, secret exclusion, non-snapshot semantics, and required upgraded
  charm revision. Check examples against the integration tests and run the
  repository's Markdown checks on `README.md`.
- [ ] 7.2 Record maintainer action-metadata approval and rollout/rollback
  verification in this change's `tasks.md`; archive the completed change
  through OpenSpec once implementation and verification are finished,
  producing `openspec/specs/oauth-client-listing/spec.md`. Validate the
  archived specs before requesting merge; do not archive planning-only work.

## Implementation Notes

Implementation and runtime verification are complete. Archival remains a
separate pre-merge step.

- Maintainer approval: Dan explicitly requested implementation of the proposed
  action contract on 2026-11-10, including the action metadata changes.
- `tox -e fmt,lint,unit` passed: 387 passed, 5 expected failures, and one
  pre-existing unexpected pass. Focused listing/CLI/action tests initially
  passed 187 cases; the additional serialization-timeout and shared fixture
  tests bring this to 191 cases.
- `charmcraft pack --platform ubuntu@22.04:amd64` passed.
- Mypy passed for all changed production and unit-test files (including the
  shared scenario fixtures and action default tests). The repository's
  all-files hook is blocked by the pre-existing `constants`/`src.constants`
  duplicate module mapping; integration-file checking reports the existing
  missing return annotation in `app_integration_data`'s nested helper.
- Verified Ops 3.9.0 flattened action argument encoding against installed
  source and tests, including UTF-8 byte and argument-terminator accounting.
- Listing command failures deliberately omit Hydra stderr and Pebble task
  logs, reporting only an exit code or generic failure. A regression test
  reproduced client-secret/metadata leakage before this was fixed.
- Live testing initially reproduced stale MicroK8s kubelet certificate SANs
  after a network change. Reissuing that certificate with the existing CA/key
  restored node proxy health and Juju connectivity; the system changelog
  records that separate environment repair.
- The background test runner required `/snap/bin` on PATH for the Juju snap.
  The corrected live run successfully deployed the charm and dependencies.
- Live pagination testing revealed that the large export fixture also made
  the default page exceed 90 KiB. Pagination now uses 32-byte metadata while
  the oversized-export fixture retains 550-byte metadata. This changes test
  setup only, not the documented action contract.
- OpenSpec remains active pending the separate pre-merge archival step.
- Independent pre-commit review passed with no blocking security or logic
  findings. Subsequent changes separate small/large integration fixtures and
  enforce the export deadline during serialization and before publication;
  a new regression test verifies timeout cleanup preserves the previous file.
- README Markdown checks report only pre-existing findings on lines 93-179;
  the added listing/export section has no Markdown violations.
- Follow-up independent review passed for separated fixtures and the stronger
  serialization/publication deadline checks; all 46 domain-helper tests pass.
- Retrieved a real 106,150-byte export from the charm container with `juju scp`:
  115 JSON records and zero client-secret fields. The integration assertion
  was corrected to check the complete JSON-encoded dummy secret value rather
  than its substring, which also occurs in `client_secret_basic`.
- First live suite: 26 passed and three test-setup/assertion failures, all
  corrected without changing the action contract. The corrected post-upgrade
  action verification passed, including empty/default listing, token paging,
  and JSON export retrieval. The corrected pagination/export/replacement
  rerun passed all three selected tests; the corrected post-upgrade rerun
  passed its selected test. Together with the 26 initially passing cases,
  every integration/upgrade case has now executed successfully. This is
  rerun evidence, not a claim that the initial full-suite invocation was green.
- Runtime stack: Juju 3.6.29 client, controller/agents 3.6.27, MicroK8s 1.36.2,
  and workload image `ghcr.io/canonical/hydra:26.2.0`.
- Both retained temporary models were removed by the successful rerun fixtures;
  `juju models --controller k8s` now lists only the controller model.
