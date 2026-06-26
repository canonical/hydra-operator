## 1. Dependencies and Project Setup

- [x] 1.1 Add `charmlibs-interfaces-istio-ingress-route==1.0.2` to `requirements.txt`
- [x] 1.2 Install the new dependency in the development environment (`pip install charmlibs-interfaces-istio-ingress-route==1.0.2`)

## 2. Update charmcraft.yaml

- [x] 2.1 Change `public-route` interface from `traefik_route` to `istio_ingress_route` in `charmcraft.yaml`
- [x] 2.2 Change `internal-route` interface from `traefik_route` to `istio_ingress_route` in `charmcraft.yaml`

## 3. Update Layer 2 – integrations.py

- [x] 3.1 Remove `TraefikRouteRequirer` import and `get_external_host_and_scheme` helper from `integrations.py`
- [x] 3.2 Add imports for `IstioIngressRouteRequirer`, `IstioIngressRouteConfig`, `Listener`, `HTTPRoute`, `HTTPRouteMatch`, `HTTPPathMatch`, `HTTPPathMatchType`, `BackendRef`, `ProtocolType` from `charmlibs.interfaces.istio_ingress_route`
- [x] 3.3 Rewrite `PublicRouteData.load()` to accept `IstioIngressRouteRequirer`, read `external_host` and `tls_enabled`, construct `url` as `https://` or `http://` accordingly, and build an `IstioIngressRouteConfig` with a single HTTPRoute covering `/oauth2` (PathPrefix), `/.well-known/jwks.json`, `/.well-known/openid-configuration`, `/.well-known/oauth-authorization-server`, `/userinfo` (all Exact)
- [x] 3.4 Rewrite `InternalIngressData.load()` to accept `IstioIngressRouteRequirer`, read `external_host` and `tls_enabled`, build an `IstioIngressRouteConfig` with two HTTPRoutes: admin (4 PathPrefix matches → port 4445) and public (PathPrefix `/oauth2` + Exact `/.well-known/jwks.json` → port 4444)
- [x] 3.5 Keep `config: IstioIngressRouteConfig` field on `InternalIngressData` and `PublicRouteData` dataclasses (used by the holistic handler to call `submit_config`); remove the old `config: dict` field type annotation
- [x] 3.6 Delete Jinja2 template files `templates/public-route.json.j2` and `templates/internal-route.json.j2`

## 4. Update Layer 1 – charm.py

- [x] 4.1 Replace `from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer` with `from charmlibs.interfaces.istio_ingress_route import IstioIngressRouteRequirer` in `charm.py`
- [x] 4.2 Replace `self.internal_ingress = TraefikRouteRequirer(...)` with `self.internal_ingress = IstioIngressRouteRequirer(self, relation_name=INTERNAL_ROUTE_INTEGRATION_NAME)` in `__init__`
- [x] 4.3 Replace `self.public_route = TraefikRouteRequirer(...)` with `self.public_route = IstioIngressRouteRequirer(self, relation_name=PUBLIC_ROUTE_INTEGRATION_NAME)` in `__init__`
- [x] 4.4 Replace the three internal-route event observations (`relation_joined`, `relation_changed`, `relation_broken`) with a single observation of `self.internal_ingress.on.ready` → `_on_internal_ingress_ready`
- [x] 4.5 Replace the three public-route event observations (`relation_joined`, `relation_changed`, `relation_broken`) with a single observation of `self.public_route.on.ready` → `_on_public_route_ready`
- [x] 4.6 Rewrite `_on_internal_ingress_joined` and `_on_internal_ingress_changed` as a single `_on_internal_ingress_ready(self, event)` handler: call `_holistic_handler(event)` (which will submit the config if leader+ready), then call `_update_hydra_endpoints(event)`
- [x] 4.7 Rewrite `_on_public_route_changed` and `_on_public_route_broken` as a single `_on_public_route_ready(self, event)` handler: call `_holistic_handler(event)` (which will submit the config if leader+ready), then call `_update_hydra_endpoints(event)` and `_on_oauth_integration_created(event)`
- [x] 4.8 In `_holistic_handler`, after the existing `ConfigFile` + `_pebble_service.plan()` block, add: if `self.unit.is_leader()` and `self.public_route.is_ready()`, call `self.public_route.submit_config(PublicRouteData.load(self.public_route).config)`; if `self.unit.is_leader()` and `self.internal_ingress.is_ready()`, call `self.internal_ingress.submit_config(InternalIngressData.load(self.internal_ingress, ...).config)`
- [x] 4.8 In `_holistic_handler`, after the existing `ConfigFile` + `_pebble_service.plan()` block, add: if `self.unit.is_leader()` and `self.public_route.is_ready()`, call `self.public_route.submit_config(PublicRouteData.load(self.public_route).config)`; if `self.unit.is_leader()` and `self.internal_ingress.is_ready()`, call `self.internal_ingress.submit_config(InternalIngressData.load(self.internal_ingress, ...).config)`
- [x] 4.9 Remove all `self.public_route._relation = event.relation` and `self.internal_ingress._relation = event.relation` workarounds (not needed with new lib)
- [x] 4.10 Remove unused `RelationJoinedEvent` import if no longer needed

## 5. Update utils.py

- [x] 5.1 Update `public_route_is_ready` to call `charm.public_route.is_ready()` (the `IstioIngressRouteRequirer.is_ready()` checks for relation existence and external host)
- [x] 5.2 Update `public_route_is_secure` to derive scheme from `charm.public_route.tls_enabled` instead of `PublicRouteData.secured` (or keep as-is if `PublicRouteData.secured` still works via `tls_enabled`)

## 6. Remove Traefik Library

- [x] 6.1 Delete the vendored Traefik library directory `lib/charms/traefik_k8s/`

## 7. Update Unit Tests

- [x] 7.1 Update `conftest.py`: change `public_route_relation_ready` fixture remote app data from `{"external_host": "example.com", "scheme": "https"}` to `{"external_host": "example.com", "tls_enabled": "True"}`
- [x] 7.2 Update `conftest.py`: change `internal_route_relation_ready` fixture remote app data from `{"external_host": "internal.com", "scheme": "https"}` to `{"external_host": "internal.com", "tls_enabled": "True"}`
- [x] 7.3 Update `test_integrations.py`: replace `TraefikRouteRequirer` mocks with `IstioIngressRouteRequirer` mocks; remove template file patching; update assertions to check `IstioIngressRouteConfig` objects instead of JSON dicts
- [x] 7.4 Update `test_charm.py`: replace `submit_to_traefik` mock assertions with `submit_config` mock assertions; update any event-handler tests for the renamed handlers (`_on_public_route_ready`, `_on_internal_ingress_ready`)
- [x] 7.5 Run `tox -e unit` and fix any remaining test failures

## 8. Update Integration Tests

- [x] 8.1 Update `tests/integration/constants.py`: replace `TRAEFIK_CHARM`, `TRAEFIK_ADMIN_APP`, `TRAEFIK_PUBLIC_APP` constants with `ISTIO_CHARM = "istio-k8s"`, `ISTIO_INGRESS_CHARM = "istio-ingress-k8s"`, `ISTIO_INGRESS_APP = "istio-ingress"` (or similar)
- [x] 8.2 Update `tests/integration/constants.py`: change `LOGIN_UI_APP` channel reference (wherever used) to deploy from `istio/edge`
- [x] 8.3 Update `test_build_and_deploy` in `tests/integration/test_charm.py`: replace the two `juju.deploy(TRAEFIK_CHARM, ...)` calls with:
  ```python
  juju.deploy("istio-k8s", channel="2/stable", trust=True)
  juju.deploy("istio-ingress-k8s", channel="2/stable", trust=True)
  juju.integrate("istio-ingress-k8s", "istio-k8s")
  ```
  and change `LOGIN_UI_APP` deploy channel to `istio/edge`
- [x] 8.4 Update `integrate_dependencies` in `tests/integration/conftest.py`: replace `juju.integrate(f"{HYDRA_APP}:{PUBLIC_ROUTE_INTEGRATION_NAME}", TRAEFIK_PUBLIC_APP)` with `juju.integrate(f"{HYDRA_APP}:{PUBLIC_ROUTE_INTEGRATION_NAME}", "istio-ingress-k8s:istio-ingress-route")`; replace the `TRAEFIK_ADMIN_APP` internal-route integration with the istio equivalent (if internal-route is also migrated to istio)
- [x] 8.5 Update `juju.wait(...)` calls: replace `TRAEFIK_PUBLIC_APP`, `TRAEFIK_ADMIN_APP` with the new istio app names
- [x] 8.6 Update `test_public_route_integration` assertions in `test_charm.py`: `scheme` field no longer exists; assert `external_host` and `tls_enabled` fields instead
- [x] 8.7 Update `test_internal_ingress_integration` assertions: replace `scheme` field check with `tls_enabled` check
- [x] 8.8 Update `public_address` fixture in `conftest.py`: replace `get_unit_address(juju, app_name=TRAEFIK_PUBLIC_APP)` with the equivalent for `istio-ingress-k8s`
- [x] 8.9 Update `test_upgrade.py`: replace Traefik deploy/integrate steps with the istio stack; update `LOGIN_UI_APP` channel to `istio/edge`

## 9. Add Migration Document

- [x] 9.1 Create `migration/traefik-to-istio-ingress.md` with step-by-step migration instructions: (1) remove Traefik relations before upgrade, (2) upgrade charm, (3) relate to istio-ingress-k8s using same relation names, plus rollback procedure

## 10. Lint and Format

- [x] 10.1 Run `tox -e fmt` to apply standard formatting
- [x] 10.2 Run `tox -e lint` and fix any violations

## 11. Fix Listener Port (Ingress Gateway Port, Not Backend Port)

- [x] 11.1 Add `INGRESS_HTTP_PORT = 80` and `INGRESS_HTTPS_PORT = 443` constants to `src/constants.py`
- [x] 11.2 Import `INGRESS_HTTP_PORT`, `INGRESS_HTTPS_PORT` in `src/integrations.py`
- [x] 11.3 Fix `PublicRouteData.load()`: derive `ingress_port` from `requirer.tls_enabled` and use `Listener(port=ingress_port, ...)` instead of `Listener(port=PUBLIC_PORT, ...)`
- [x] 11.4 Fix `InternalIngressData.load()`: replace two listeners (`admin_listener` + `public_listener`) with a single `listener` on the ingress port; update both HTTPRoutes to bind to that single listener
- [x] 11.5 Update unit tests in `test_integrations.py` to assert correct listener port (80 for `tls_enabled=False`, 443 for `tls_enabled=True`)
