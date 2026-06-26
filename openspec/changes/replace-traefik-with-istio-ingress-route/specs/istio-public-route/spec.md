## ADDED Requirements

### Requirement: Public API paths are routed via Istio HTTPRoute

The charm SHALL submit an `IstioIngressRouteConfig` to the `public-route` relation inside `_holistic_handler` when `self.unit.is_leader()` and `self.public_route.is_ready()`. The config SHALL define a single HTTP listener on port 4444 and a single `HTTPRoute` with the following matches targeting the Hydra public service (`<app>.<model>.svc.cluster.local:4444`):

- `PathPrefix` match on `/oauth2`
- `Exact` match on `/.well-known/jwks.json`
- `Exact` match on `/.well-known/openid-configuration`
- `Exact` match on `/.well-known/oauth-authorization-server`
- `Exact` match on `/userinfo`

#### Scenario: Submit config on holistic handler when leader and ready

- **WHEN** `_holistic_handler` runs, the unit is the leader, and `public_route.is_ready()` is `True`
- **THEN** the charm calls `public_route.submit_config()` with an `IstioIngressRouteConfig` containing the five path matches targeting port 4444

#### Scenario: Config not submitted when not leader

- **WHEN** `_holistic_handler` runs and the unit is NOT the leader
- **THEN** the charm does NOT call `submit_config()` on the public route

#### Scenario: Config not submitted when public route not ready

- **WHEN** `_holistic_handler` runs, the unit is the leader, but `public_route.is_ready()` is `False`
- **THEN** the charm does NOT call `submit_config()` on the public route

### Requirement: Public route ready event delegates to holistic handler and updates endpoints

When the `public-route` relation fires `on.ready`, the charm SHALL call `_holistic_handler` (which submits the config) and SHALL call `_update_hydra_endpoints`.

#### Scenario: Holistic handler and endpoint update triggered on public route ready

- **WHEN** the `public-route` relation fires `on.ready`
- **THEN** `_holistic_handler` is called and `hydra_endpoints_provider.send_endpoint_relation_data` is called with the current endpoints

### Requirement: Public URL is derived from Istio external host

The `PublicRouteData` SHALL read `external_host` and `tls_enabled` from the `IstioIngressRouteRequirer`. The public URL SHALL be constructed as `https://<external_host>` if `tls_enabled` is `True`, and `http://<external_host>` otherwise.

#### Scenario: URL constructed with TLS enabled

- **WHEN** `IstioIngressRouteRequirer.tls_enabled` is `True` and `external_host` is `"example.com"`
- **THEN** `PublicRouteData.url` equals `URL("https://example.com")` and `PublicRouteData.secured` returns `True`

#### Scenario: URL constructed without TLS

- **WHEN** `IstioIngressRouteRequirer.tls_enabled` is `False` and `external_host` is `"example.com"`
- **THEN** `PublicRouteData.url` equals `URL("http://example.com")` and `PublicRouteData.secured` returns `False`

#### Scenario: No external host means not ready

- **WHEN** `IstioIngressRouteRequirer.external_host` returns an empty string
- **THEN** `PublicRouteData.is_ready()` returns `False`

### Requirement: hydra-endpoint-info and OAuth provider info updated when public URL changes

The charm SHALL call `_update_hydra_endpoints` and `_on_oauth_integration_created` when the `public-route` ready event fires, to propagate the new URL to the `hydra-endpoint-info` databag and OAuth provider info. This is separate from the holistic handler call.

#### Scenario: Endpoint info and OAuth info updated on public route ready

- **WHEN** the `public-route` relation fires `on.ready`
- **THEN** `hydra_endpoints_provider.send_endpoint_relation_data` is called with the current admin and public endpoints and OAuth provider info is updated

### Requirement: Broken public route triggers holistic handler

When the `public-route` relation is removed (`on.ready` emitted on `relation_broken`), the charm SHALL run the holistic handler to reflect the missing ingress.

#### Scenario: Holistic handler triggered when public route removed

- **WHEN** the `public-route` relation is broken
- **THEN** the holistic handler runs
