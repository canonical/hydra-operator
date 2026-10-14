## Why

The charm serves the public endpoints of Hydra at the root of the host of the gateway. Two Hydras cannot use the same host, because their public paths are the same.

The feature "Bring Your Own SSO" adds a second Hydra. The deployment serves the two Hydras and the login UI on one host.

## What Changes

- A new option, `public_path_prefix`. When it has a value, the charm serves the public endpoints of Hydra under that path.
- The gateway rewrites each path to the path of Hydra before it sends the request to Hydra.
- The issuer and the public URL of Hydra have the prefix. The URLs that the charm publishes on `oauth` also have the prefix.
- The session cookie of Hydra has the prefix as its path. Thus the second Hydra does not remove the session cookie of the first Hydra.
- A prefix that is not a path blocks the charm.

Without the option, the charm does not change its route, Hydra's configuration or the URLs that it publishes.

## Capabilities

### New Capabilities

- `public-path-prefix`: the public endpoints of Hydra under a path of the host of the gateway.

### Modified Capabilities

None.

## Non-goals

- A prefix for the admin endpoints or for the relation `internal-route`.
- A check of the gateway. The charm does not find a path that another application also uses.
- A change of the prefix without effect on clients. A new prefix gives a new issuer. Tokens from before have the old issuer.

## Success Metrics

- With `public_path_prefix=/sso`, `https://<host>/sso/.well-known/openid-configuration` returns a document with the issuer `https://<host>/sso`.
- Two Hydras on one gateway, one of them with a prefix, both complete sign-ins on the same host. A sign-in through one Hydra does not remove the session of the other.
- Without the option, the route and Hydra's configuration do not change.

## Impact

- `charmcraft.yaml`: the option `public_path_prefix`.
- `src/configs.py`: `CharmConfig.public_path_prefix`, the prefix with one slash at the start.
- `src/integrations.py`: `PublicRouteData` makes the routes, the rewrites and the public URL from the prefix.
- `src/utils.py`, `src/charm.py`, `src/constants.py`: the check of the prefix, the status, and the prefix in each use of `PublicRouteData`.
- `templates/hydra.yaml.j2`: the key `serve.cookies.paths.session`.
- `README.md`: a paragraph about the option.
- `tests/unit`: tests of the prefix, the routes, the published URLs, the cookie path and the status.
