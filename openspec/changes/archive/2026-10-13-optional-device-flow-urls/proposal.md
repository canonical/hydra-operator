## Why

The charm waits for 5 URLs of the login UI on the relation `ui-endpoint-info` before it takes the login UI as ready. A login UI without the device flow publishes only the login, consent and error URLs. For such a login UI, the charm never writes Hydra's configuration and never starts Hydra.

The SSO Service is such a login UI. In the feature "Bring Your Own SSO", it is the login and consent provider of a second Hydra, and it has no device flow.

## What Changes

- The charm needs only 3 URLs from the login UI: `login_url`, `consent_url` and `oidc_error_url`.
- The 2 device-flow URLs, `device_verification_url` and `post_device_done_url`, become optional.
- The charm writes `urls.device.verification` and `urls.device.success` to Hydra's configuration only for the device-flow URLs that the login UI publishes.
- When the login UI publishes no device-flow URL, Hydra's configuration has no `urls.device` key. Hydra then uses its own fallback pages for the device flow.

A login UI that publishes all 5 URLs gets the same configuration as before.

## Capabilities

### New Capabilities

- `login-ui-endpoints`: the URLs that the charm reads from the login UI, and how it writes them to Hydra's configuration.

### Modified Capabilities

- `workload-service`: which URLs of the login UI the charm needs before it runs Hydra.

## Non-goals

- A check of the URLs. The charm does not validate a URL or make sure that the login UI serves it.
- A switch for the device flow of Hydra. The charm does not turn the device flow off when the login UI publishes no device-flow URL.
- A stop of the workload when the login UI no longer publishes a required URL. The workload continues with its configuration.

## Success Metrics

- With a login UI that publishes no device-flow URL, the unit shows `active` and Hydra runs.
- With a login UI that publishes all 5 URLs, Hydra's configuration does not change.

## Impact

- `src/integrations.py`: `LoginUIEndpointData.is_ready` checks only the 3 required URLs.
- `templates/hydra.yaml.j2`: the key `urls.device` and each of its 2 keys are conditional.
- `tests/unit`: tests of readiness with and without the device-flow URLs, and of the configuration with both, with one and with none of them.
- The library `login_ui_endpoints` does not change. Each field of its provider data is already optional.
- `charmcraft.yaml` and the options of the charm do not change.
