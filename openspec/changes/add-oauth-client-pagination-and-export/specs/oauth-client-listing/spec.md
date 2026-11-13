# OAuth client listing

## Purpose

Allow operators to inspect every registered OAuth client through paginated
listing or a complete downloadable export, without changing the default
listing response or exposing client secrets.

## ADDED Requirements

### Requirement: Backward-compatible default listing

The `list-oauth-clients` action SHALL return one page of at most 100 clients
when invoked without parameters. The `clients` result SHALL remain a JSON
string containing an array with the existing field names and serialization.
The action SHALL NOT automatically retrieve all pages unless export is
requested. Existing successful default invocations SHALL remain compatible;
a successfully retrieved empty inventory SHALL now succeed rather than fail.

#### Scenario: More than 100 clients exist

- **WHEN** an operator invokes the action without parameters on a ready unit
  containing more than 100 registered clients
- **THEN** `clients` SHALL contain the first page of at most 100 clients
- **AND** the result SHALL contain a non-empty `next-page-token`

#### Scenario: Inventory is empty

- **WHEN** Hydra successfully returns an empty inventory
- **THEN** the action SHALL succeed with `clients` equal to the JSON string `[]`
- **AND** `next-page-token` SHALL be absent

### Requirement: Operator-controlled pagination

The action SHALL accept optional `page-size` and `page-token` parameters.
`page-size` SHALL be an integer greater than zero, defaulting to 100.
`page-token` SHALL be a string, defaulting to the first page when absent or
empty. A non-empty token SHALL be passed unchanged to Hydra. The action SHALL
return `next-page-token` only when Hydra supplies a non-empty continuation
token, and SHALL NOT return `is-last-page`.

#### Scenario: Operator requests another page

- **WHEN** an operator supplies a supported `page-size` and a token from a
  previous successful response
- **THEN** the action SHALL return the requested page in `clients`
- **AND** the supplied page size and token SHALL be used for that request

#### Scenario: No continuation is available

- **WHEN** Hydra returns a page without a non-empty continuation token
- **THEN** `next-page-token` SHALL be absent
- **AND** callers SHALL be able to identify completion without another flag

#### Scenario: Short page still has a continuation token

- **WHEN** Hydra returns fewer clients than requested but supplies a
  non-empty continuation token
- **THEN** the action SHALL return that token rather than infer completion
  from the number of clients

#### Scenario: Invalid page size or token

- **WHEN** an operator supplies a non-integer, zero, or negative page size,
  a non-string token, or a pagination value rejected by Hydra
- **THEN** the action SHALL fail with an actionable pagination error
- **AND** it SHALL NOT report a successful client list

### Requirement: Explicit complete JSON export

The action SHALL accept an optional string parameter `export`, with `json`
as the only supported value. Omitting the parameter SHALL select inline
listing. With `export=json`, the action SHALL retrieve every page starting
from the first page and write a UTF-8 JSON array containing the same client
representation as inline listing. In export mode `page-size` SHALL determine
the fetch batch size. Successful export results SHALL contain `export-path`,
`export-unit`, `export-container`, and `client-count`, and SHALL NOT contain
`clients`, `next-page-token`, or `is-last-page`.

#### Scenario: Export spans multiple pages

- **WHEN** an operator requests `export=json` for an unchanged inventory
  containing more than 100 clients
- **THEN** the completed file SHALL contain every client returned across
  Hydra's pages, including clients absent from the first page
- **AND** `client-count` SHALL match the number of array entries
- **AND** the action results SHALL contain only retrieval metadata and count

#### Scenario: Export uses a custom batch size

- **WHEN** an operator requests `export=json` with a supported `page-size`
- **THEN** each page request SHALL use that batch size
- **AND** the export SHALL continue until no continuation token remains

#### Scenario: Export of an empty inventory

- **WHEN** an operator requests `export=json` and Hydra successfully returns
  an empty inventory
- **THEN** the action SHALL succeed with a file containing `[]`
- **AND** `client-count` SHALL be zero

#### Scenario: Unsupported export value

- **WHEN** an operator supplies an export value other than `json`, including
  an empty string or the former proposed boolean value `true`
- **THEN** the action SHALL fail and identify `json` as the supported format
- **AND** it SHALL NOT create an export

#### Scenario: Export conflicts with a starting token

- **WHEN** an operator supplies `export=json` and a non-empty `page-token`
- **THEN** the action SHALL fail before fetching clients or creating a file
- **AND** the error SHALL explain that export always starts from the first page

### Requirement: Downloadable temporary export

A successful export SHALL be retrievable with `juju scp` from the exact unit,
container, and absolute path returned by the action. The file SHALL reside
in the charm container. Each unit SHALL retain at most its latest successful
export, with a maximum export size of 100 MiB. A later successful export
SHALL replace the previous one; a failed export SHALL preserve it. Exports
SHALL be documented as temporary and not guaranteed to survive unit
replacement, and operators SHALL be told to retrieve them before exporting
again on that unit.

#### Scenario: Operator retrieves an export

- **WHEN** an operator uses `juju scp --container charm` with the returned
  unit and export path before replacement or another successful export
- **THEN** the downloaded file SHALL contain the complete JSON export
- **AND** retrieval SHALL NOT depend on which unit is currently leader

#### Scenario: Later export succeeds or fails

- **WHEN** an operator runs another export on the same unit
- **THEN** a successful export SHALL replace the previous completed file
- **AND** a failed export SHALL leave the previous completed file unchanged

### Requirement: Client secret exclusion

Both inline listing and export SHALL exclude the OAuth client secret field.
The charm SHALL NOT log client contents or include them in action failure
messages. Export files SHALL be accessible only to the owning operating
system user by default, without restricting authorized Juju retrieval.

#### Scenario: Client response contains a secret

- **WHEN** Hydra returns an OAuth client with a client secret field
- **THEN** that field SHALL be absent from inline results and exported JSON
- **AND** it SHALL NOT appear in logs or action failure messages

### Requirement: Complete results or explicit failure

The action SHALL fail clearly if the service is not ready, a page cannot be
fetched or validated, pagination repeats a continuation token, or export
creation fails. It SHALL NOT advertise an incomplete export as successful.
Inline results SHALL be bounded to a conservative 90 KiB inline action
result budget, including result keys and continuation metadata.
Oversized inline results SHALL fail without truncation and
suggest a smaller page size or `export=json`. Exports exceeding 100 MiB
SHALL fail, remove incomplete output, and preserve the previous export.

#### Scenario: Unit is not ready

- **WHEN** the action runs while the Hydra service is not ready
- **THEN** it SHALL fail with an instruction to retry once the service is ready

#### Scenario: Inline page exceeds the result budget

- **WHEN** the inline result exceeds 90 KiB
- **THEN** the action SHALL fail without returning a truncated client array
- **AND** the error SHALL suggest a smaller `page-size` or `export=json`

#### Scenario: A later page fails or pagination cycles

- **WHEN** an export encounters a failed or malformed page, a timeout,
  or a repeated non-empty continuation token
- **THEN** the action SHALL fail without returning success metadata
- **AND** incomplete output SHALL be removed
- **AND** the previous completed export SHALL remain unchanged

#### Scenario: File cannot be completed within the resource budget

- **WHEN** writing an export fails or the export exceeds 100 MiB
- **THEN** the action SHALL fail with an actionable error without client data
- **AND** incomplete output SHALL be removed
- **AND** the previous completed export SHALL remain unchanged
