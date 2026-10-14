## 1. The option

- [x] 1.1 In `charmcraft.yaml`, add the option `public_path_prefix`, a string that is empty by default
- [x] 1.2 In `src/configs.py`, add `CharmConfig.public_path_prefix`, with one slash at the start and no slash at the end
- [x] 1.3 In `src/utils.py` and `src/constants.py`, add the condition `public_path_prefix_is_valid` to `NOOP_CONDITIONS`
- [x] 1.4 In `src/charm.py`, set the status `blocked` for an incorrect prefix and send no route for it
- [x] 1.5 In `tests/unit/test_configs.py` and `tests/unit/test_charm.py`, add unit tests of the prefix and of the status

## 2. The route and the URLs

- [x] 2.1 In `src/integrations.py`, with a prefix, make `PublicRouteData` send one rewritten rule for each public path
- [x] 2.2 In `src/integrations.py`, add the prefix to the public URL of `PublicRouteData`
- [x] 2.3 In `src/charm.py` and `src/utils.py`, give the prefix to each use of `PublicRouteData`
- [x] 2.4 In `tests/unit/test_integrations.py`, test the rules, the rewrites and the public URL with a prefix
- [x] 2.5 In `tests/unit/test_charm.py`, test the URLs that the charm publishes on `oauth` with a prefix

## 3. The session cookie

- [x] 3.1 In `templates/hydra.yaml.j2`, write `serve.cookies.paths.session` only when there is a prefix
- [x] 3.2 In `tests/unit/test_configs.py`, add unit tests of the configuration with and without a prefix

## 4. Verification suite

- [x] 4.1 Run `tox -e lint`
- [x] 4.2 Run `tox -e unit` and make sure that all tests pass
- [x] 4.3 Without the option, compare the route and Hydra's configuration with those before the change
- [x] 4.4 Run `openspec validate --all --strict`

## 5. Documentation & rollout

- [x] 5.1 In `README.md`, add one paragraph about the option

This change needs no rollout step. Without the option, the charm does not change its behaviour.

## Implementation Notes

The implementation follows the plan. There are no deviations.
