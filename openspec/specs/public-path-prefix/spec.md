# public-path-prefix Specification

## Purpose

The charm serves the public endpoints of Hydra through the relation `public-route`. By default, the endpoints are at the root of the host of the gateway. Two Hydras cannot then use the same host, because their public paths are the same. This capability lets an operator serve the public endpoints of Hydra under a path of that host.

The feature "Bring Your Own SSO" uses this capability. Its second Hydra is under a path, on the host of the login UI and of the first Hydra.

Key decisions:

- **The gateway rewrites the path.** Hydra serves its endpoints at its root. The charm does not change the paths of Hydra. It tells the gateway to remove the prefix before it sends a request to Hydra.
- **The issuer has the prefix.** Hydra makes its endpoints from its public URL. Thus the discovery document, the tokens and the published URLs all have the prefix.
- **The session cookie has the prefix as its path.** Two Hydras on one host give their session cookies the same name. A Hydra that does not remember a login removes its session cookie. With the prefix as the path, it removes only its own cookie.
- **An option, not a relation.** The operator decides how a deployment exposes Hydra. No related application knows that.

Non-goals:

- A prefix for the admin endpoints or for the relation `internal-route`.
- A check of the gateway. The charm does not find a path that another application also uses.

## Requirements
### Requirement: The public endpoints under a path prefix

The charm SHALL read the option `public_path_prefix`. The charm SHALL remove the spaces and the slashes at the start and at the end of the value. When the result is not empty, the charm SHALL put one slash at its start. In this specification, the prefix is this result. An empty value gives no prefix.

Without a prefix, the charm SHALL send one rule to the relation `public-route`. That rule has the 5 public paths of Hydra, at the root of the host.

When there is a prefix, the charm SHALL send one rule for each public path of Hydra. Each rule SHALL match the prefix and then the path. Each rule SHALL tell the gateway to change the path of the request to the path of Hydra, as this table shows:

| path on the gateway | path that Hydra gets |
|---|---|
| `<prefix>/oauth2`, and each path under it | `/oauth2`, and the same path under it |
| `<prefix>/.well-known/jwks.json` | `/.well-known/jwks.json` |
| `<prefix>/.well-known/openid-configuration` | `/.well-known/openid-configuration` |
| `<prefix>/.well-known/oauth-authorization-server` | `/.well-known/oauth-authorization-server` |
| `<prefix>/userinfo` | `/userinfo` |

Without the prefix, the gateway does not send these paths to this Hydra. Thus a second Hydra can use the paths at the root of the same host.

This behaviour is backward compatible. Without the option, the route does not change.

#### Scenario: No prefix

- **WHEN** the option `public_path_prefix` is empty
- **THEN** the route has one rule with the 5 public paths at the root of the host

#### Scenario: A prefix

- **WHEN** the option `public_path_prefix` is `/sso`
- **THEN** the gateway sends `/sso/oauth2/auth` to Hydra as `/oauth2/auth`
- **AND** the gateway sends `/sso/.well-known/openid-configuration` to Hydra as `/.well-known/openid-configuration`

#### Scenario: Slashes around the value

- **WHEN** the option `public_path_prefix` is `sso/` or `/sso/`
- **THEN** the prefix is `/sso`

### Requirement: The issuer and the published URLs with the prefix

The charm SHALL make the public URL from the scheme of the gateway, the host of the gateway and the prefix. The charm SHALL write the public URL to Hydra's configuration as `urls.self.issuer` and `urls.self.public`. The charm SHALL make each URL that it publishes on the relation `oauth` from the public URL. Thus the issuer and the public endpoints have the prefix.

When the prefix changes, the issuer changes. A client must then use the new issuer. Tokens that Hydra issued before have the old issuer.

#### Scenario: The issuer with a prefix

- **WHEN** the option `public_path_prefix` is `/sso`
- **AND** the gateway publishes the host `example.com` with TLS
- **THEN** the charm publishes the issuer `https://example.com/sso` on `oauth`
- **AND** the charm publishes the authorization endpoint `https://example.com/sso/oauth2/auth`

#### Scenario: The issuer without a prefix

- **WHEN** the option `public_path_prefix` is empty
- **AND** the gateway publishes the host `example.com` with TLS
- **THEN** the charm publishes the issuer `https://example.com` on `oauth`

### Requirement: The session cookie under the prefix

When there is a prefix, the charm SHALL write the prefix to Hydra's configuration as `serve.cookies.paths.session`. When there is no prefix, the charm SHALL NOT write the key `serve.cookies`.

Two Hydras on the same host give their session cookies the same name. Hydra removes its session cookie after each login that it does not remember. With the path of the cookie at the root, a Hydra under a prefix removes the session cookie of the Hydra at the root. With the prefix as the path, a Hydra removes only its own session cookie.

#### Scenario: The cookie path with a prefix

- **WHEN** the option `public_path_prefix` is `/sso`
- **THEN** Hydra's configuration has `serve.cookies.paths.session` with the value `/sso`

#### Scenario: No cookie path without a prefix

- **WHEN** the option `public_path_prefix` is empty
- **THEN** Hydra's configuration has no `serve.cookies` key

### Requirement: An incorrect prefix blocks the charm

Each segment of the prefix SHALL contain only letters, digits, `-` and `_`. For a prefix with another character, the charm SHALL set the status `blocked` with the message `Invalid configuration: public_path_prefix`. While the prefix is incorrect, the charm SHALL NOT send a new route and SHALL NOT write Hydra's configuration. The workload continues with its last configuration.

#### Scenario: A space in the prefix

- **WHEN** the option `public_path_prefix` is `s s`
- **THEN** the status of the unit is `blocked` with the message `Invalid configuration: public_path_prefix`
- **AND** the charm does not change the route or Hydra's configuration

