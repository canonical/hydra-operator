## Why

The hydra-operator currently uses `traefik_route` integrations for ingress, but deployments are migrating to Istio-based networking. The `charmlibs-interfaces-istio-ingress-route` library provides a first-class, typed interface for publishing HTTPRoute configurations to the `istio-ingress-k8s` charm, replacing the raw Traefik JSON templates.

## What Changes

- Replace `TraefikRouteRequirer` (from `charms.traefik_k8s.v0.traefik_route`) with `IstioIngressRouteRequirer` (from `charmlibs.interfaces.istio_ingress_route`) for both `public-route` and `internal-route` integrations.
- Keep integration names `public-route` and `internal-route` unchanged.
- Change `charmcraft.yaml` interface type for both integrations from `traefik_route` to `istio_ingress_route`.
- Add `charmlibs-interfaces-istio-ingress-route==1.0.2` to `requirements.txt`.
- Replace Jinja2 JSON templates (`public-route.json.j2`, `internal-route.json.j2`) with typed `IstioIngressRouteConfig` objects built from the `charmlibs` interface models.
- Map existing Traefik routes to Istio `HTTPRoute` resources: consolidate multiple path matchers into single HTTPRoute objects per backend where possible.
- Maintain same logic for updating the `hydra-endpoint-info` databag when the ingress URL changes.
- **BREAKING**: Remove the Traefik `lib/charms/traefik_k8s/` library from the charm (consumers must migrate).
- Add `migration/` documentation describing the upgrade path.

## Capabilities

### New Capabilities

- `istio-public-route`: Expose Hydra public API (port 4444) paths (`/oauth2`, `/.well-known/jwks.json`, `/.well-known/openid-configuration`, `/.well-known/oauth-authorization-server`, `/userinfo`) via Istio HTTPRoute through the `public-route` relation.
- `istio-internal-route`: Expose Hydra admin API (port 4445) paths (`/admin/oauth2`, `/admin/clients`, `/admin/trust`, `/admin/keys`) and public API paths (`/oauth2`, `/.well-known/jwks.json`) via Istio HTTPRoute through the `internal-route` relation.
- `ingress-migration-guide`: Document the migration path from Traefik to Istio ingress.

### Modified Capabilities

<!-- No existing spec-level capability requirements are changing. -->

## Impact

- **`src/integrations.py`**: Replace `InternalIngressData.load()` and `PublicRouteData.load()` to use `IstioIngressRouteRequirer` instead of `TraefikRouteRequirer`. Remove Jinja2 template rendering.
- **`src/charm.py`**: Replace `TraefikRouteRequirer` instantiation and event handlers (`_on_public_route_changed`, `_on_internal_ingress_joined`, `_on_internal_ingress_changed`) to use the new requirer and its `on.ready` event.
- **`src/utils.py`**: Update `public_route_is_ready` and `public_route_is_secure` to use the new interface.
- **`charmcraft.yaml`**: Change interface names for `public-route` and `internal-route` from `traefik_route` to `istio_ingress_route`. *(Requires explicit user approval before modification.)*
- **`requirements.txt`**: Add `charmlibs-interfaces-istio-ingress-route==1.0.2`.
- **`templates/`**: Remove `public-route.json.j2` and `internal-route.json.j2`.
- **`lib/charms/traefik_k8s/`**: Remove vendored Traefik library.
- **`tests/unit/conftest.py`** and **`tests/unit/test_charm.py`**: Update fixtures and tests to use new relation databag format (`external_host`, `tls_enabled` instead of `external_host`, `scheme`).
- **`migration/`**: Add `traefik-to-istio-ingress.md` migration guide.
