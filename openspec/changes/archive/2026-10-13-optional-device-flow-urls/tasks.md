## 1. Readiness of the login UI

- [x] 1.1 In `src/integrations.py`, make `LoginUIEndpointData.is_ready` need only `login_url`, `consent_url` and `oidc_error_url`
- [x] 1.2 In `tests/unit/test_integrations.py`, add unit tests of readiness with and without the device-flow URLs, and without each required URL

## 2. Hydra's configuration

- [x] 2.1 Write the key `urls.device` in `templates/hydra.yaml.j2` only when the login UI publishes a device-flow URL
- [x] 2.2 In `templates/hydra.yaml.j2`, write each of `urls.device.verification` and `urls.device.success` only when the login UI publishes its URL
- [x] 2.3 In `tests/unit/test_configs.py`, add unit tests of the configuration with both device-flow URLs, with one and with none
- [x] 2.4 In `tests/unit/test_charm.py`, add unit tests of the charm with a login UI that publishes no device-flow URL
- [x] 2.5 In `tests/unit/test_charm.py`, add unit tests of the charm with a login UI that publishes both device-flow URLs

## 3. Verification suite

- [x] 3.1 Run `tox -e lint`
- [x] 3.2 Run `tox -e unit` and make sure that all tests pass
- [x] 3.3 Run `openspec validate --all --strict`

## 4. Documentation & rollout

- [x] 4.1 Make sure that `README.md` names no URL of the login UI and needs no update

This change needs no rollout step. With a login UI that publishes all 5 URLs, Hydra's configuration does not change.

## Implementation Notes

The implementation follows the plan. There are no deviations.
