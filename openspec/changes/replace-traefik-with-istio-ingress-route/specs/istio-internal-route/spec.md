## ADDED Requirements

### Requirement: Internal admin and public paths are routed via Istio HTTPRoute

The charm SHALL submit an `IstioIngressRouteConfig` to the `internal-route` relation inside `_holistic_handler` when `self.unit.is_leader()` and `self.internal_ingress.is_ready()`. The config SHALL define two HTTP listeners (port 4445 for admin, port 4444 for public) and two `HTTPRoute` objects:

**Admin HTTPRoute** (backend: `<app>.<model>.svc.cluster.local:4445`):
- `PathPrefix` match on `/admin/oauth2`
- `PathPrefix` match on `/admin/clients`
- `PathPrefix` match on `/admin/trust`
- `PathPrefix` match on `/admin/keys`

**Public HTTPRoute** (backend: `<app>.<model>.svc.cluster.local:4444`):
- `PathPrefix` match on `/oauth2`
- `Exact` match on `/.well-known/jwks.json`

#### Scenario: Submit config on holistic handler when leader and ready

- **WHEN** `_holistic_handler` runs, the unit is the leader, and `internal_ingress.is_ready()` is `True`
- **THEN** the charm calls `internal_ingress.submit_config()` with an `IstioIngressRouteConfig` containing admin and public HTTPRoutes with the specified path matches

#### Scenario: Config not submitted when not leader

- **WHEN** `_holistic_handler` runs and the unit is NOT the leader
- **THEN** the charm does NOT call `submit_config()` on the internal ingress

#### Scenario: Config not submitted when internal route not ready

- **WHEN** `_holistic_handler` runs, the unit is the leader, but `internal_ingress.is_ready()` is `False`
- **THEN** the charm does NOT call `submit_config()` on the internal ingress

### Requirement: Internal route ready event delegates to holistic handler and updates endpoints

When the `internal-route` relation fires `on.ready`, the charm SHALL call `_holistic_handler` (which submits the config) and SHALL call `_update_hydra_endpoints`.

#### Scenario: Holistic handler and endpoint update triggered on internal route ready

- **WHEN** the `internal-route` relation fires `on.ready`
- **THEN** `_holistic_handler` is called and `hydra_endpoints_provider.send_endpoint_relation_data` is called with the current endpoints

### Requirement: Internal ingress endpoints respect use_ingress_for_relations config

When `use_ingress_for_relations` is `True` and the `internal-route` relation is ready with an external host, `InternalIngressData.public_endpoint` and `InternalIngressData.admin_endpoint` SHALL use the external hostname. When `use_ingress_for_relations` is `False` or the relation is not ready, in-cluster Kubernetes service addresses SHALL be used.

#### Scenario: External endpoints when use_ingress_for_relations is True

- **WHEN** `use_ingress_for_relations` is `True`, `external_host` is `"internal.example.com"`, and `tls_enabled` is `True`
- **THEN** both `public_endpoint` and `admin_endpoint` equal `URL("https://internal.example.com")`

#### Scenario: In-cluster endpoints when use_ingress_for_relations is False

- **WHEN** `use_ingress_for_relations` is `False`
- **THEN** `public_endpoint` equals `URL("http://<app>.<model>.svc.cluster.local:4444")` and `admin_endpoint` equals `URL("http://<app>.<model>.svc.cluster.local:4445")`

#### Scenario: In-cluster endpoints when internal route not present

- **WHEN** the `internal-route` relation does not exist
- **THEN** `public_endpoint` equals `URL("http://<app>.<model>.svc.cluster.local:4444")` and `admin_endpoint` equals `URL("http://<app>.<model>.svc.cluster.local:4445")`

### Requirement: hydra-endpoint-info is updated when internal route changes

The charm SHALL call `_update_hydra_endpoints` when the `internal-route` ready event fires (separately from the holistic handler), to propagate updated endpoints to the `hydra-endpoint-info` databag.

#### Scenario: Endpoint info updated on internal route ready

- **WHEN** the `internal-route` relation fires `on.ready`
- **THEN** `hydra_endpoints_provider.send_endpoint_relation_data` is called with the current admin and public endpoints

### Requirement: Broken internal route falls back to in-cluster endpoints

When the `internal-route` relation is broken, the charm SHALL update hydra endpoints to use in-cluster service addresses.

#### Scenario: In-cluster endpoints used when internal route broken

- **WHEN** the `internal-route` relation is broken
- **THEN** `hydra_endpoints_provider.send_endpoint_relation_data` is called with in-cluster service URLs
