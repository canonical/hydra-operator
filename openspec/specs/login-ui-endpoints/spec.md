# login-ui-endpoints Specification

## Purpose

Hydra redirects a browser to a login UI for login, for consent, for an error and for the device flow. In this specification, the login UI is the application that the charm relates to over `ui-endpoint-info`. This capability says which URLs of the login UI the charm reads, and how the charm writes the URLs to Hydra's configuration. The capability `workload-service` says which of these URLs the charm needs before it runs Hydra.

Key decisions:

- **The charm needs only the login, consent and error URLs.** A login UI without the device flow publishes no device-flow URL. Hydra must start with such a login UI. The SSO Service of "Bring Your Own SSO" is an example of such a login UI.
- **The charm leaves out the key of an unpublished device-flow URL.** With an empty URL, that key has no value in Hydra's configuration. The configuration schema of Hydra takes only a text for that key. The charm relies on Hydra to use its own fallback page for a device-flow URL that Hydra's configuration does not have.

Non-goals:

- A check of the URLs. The charm does not validate a URL and does not make sure that the login UI serves it.
- A switch for the device flow of Hydra. The charm does not turn the device flow off when the login UI publishes no device-flow URL.

## Requirements

### Requirement: The login UI URLs in Hydra's configuration

The charm SHALL read the URLs of the login UI from the application data of the relation `ui-endpoint-info`, which has the interface `login_ui_endpoints`. The login UI publishes a URL when the field of that URL has a value that is not empty. The charm SHALL write the URLs of the login UI to Hydra's configuration, the file `/etc/config/hydra.yaml` in the workload container, as this table shows:

| field of `ui-endpoint-info` | key of Hydra's configuration |
|---|---|
| `login_url` | `urls.login` |
| `consent_url` | `urls.consent` |
| `oidc_error_url` | `urls.error` |
| `device_verification_url` | `urls.device.verification` |
| `post_device_done_url` | `urls.device.success` |

The charm does not read the other fields of the relation, for example `error_url`.

The charm SHALL write each of the 2 keys under `urls.device` only when the login UI publishes the URL of that key. The charm SHALL NOT write such a key with an empty value. When the login UI publishes no device-flow URL, the charm SHALL NOT write the key `urls.device`.

For a device-flow URL that Hydra's configuration does not have, Hydra uses its own fallback page. The charm relies on that behaviour of Hydra.

This behaviour is backward compatible. A login UI that publishes all 5 URLs gets the same configuration as it got when the charm needed all 5 URLs.

When the login UI changes the URLs that it publishes, the charm SHALL render Hydra's configuration again from the new set of URLs. When the result differs from the file in the workload container, the charm SHALL write the file and restart the workload. This applies while the requirements of Hydra are met.

#### Scenario: No device-flow URL

- **WHEN** the login UI publishes neither `device_verification_url` nor `post_device_done_url`
- **THEN** Hydra's configuration has the keys `urls.login`, `urls.consent` and `urls.error`
- **AND** Hydra's configuration has no `urls.device` key

#### Scenario: Both device-flow URLs

- **WHEN** the login UI publishes `device_verification_url` and `post_device_done_url`
- **THEN** `urls.device.verification` has the value of `device_verification_url`
- **AND** `urls.device.success` has the value of `post_device_done_url`

#### Scenario: Only one device-flow URL

- **WHEN** the login UI publishes `device_verification_url` and no `post_device_done_url`
- **THEN** `urls.device` has the key `verification` and no key `success`

#### Scenario: The login UI publishes the device-flow URLs later

- **WHEN** the workload runs with a configuration that has no `urls.device` key
- **AND** the login UI then publishes both device-flow URLs
- **THEN** the charm writes Hydra's configuration again, with both keys under `urls.device`
- **AND** the charm restarts the workload

