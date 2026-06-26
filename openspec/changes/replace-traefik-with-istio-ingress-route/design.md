## Context

The hydra-operator currently uses `charms.traefik_k8s.v0.traefik_route.TraefikRouteRequirer` for ingress via two relations: `public-route` (required, exposes the OAuth2 public API) and `internal-route` (optional, exposes the admin API and public API internally). The routing configuration is expressed as raw Traefik-specific JSON rendered from Jinja2 templates.

The Canonical Identity Team is migrating to Istio-based networking. The `charmlibs-interfaces-istio-ingress-route` package provides a typed, first-class Python API for publishing Kubernetes Gateway API-compatible HTTPRoute configurations to the `istio-ingress-k8s` charm.

**Constraints:**
- Integration names `public-route` and `internal-route` MUST remain unchanged.
- The same endpoints and paths MUST be exposed.
- The `hydra-endpoint-info` databag MUST be updated whenever the ingress URL changes.
- `charmcraft.yaml` cannot be modified without explicit user approval.
- The 3-layer architecture (Layer 1: charm.py, Layer 2: integrations.py, Layer 3: ops/platform) MUST be preserved.

## Goals / Non-Goals

**Goals:**
- Replace `TraefikRouteRequirer` with `IstioIngressRouteRequirer` in both integrations.
- Preserve identical HTTP path exposure semantics.
- Maintain all existing charm behavior: `hydra-endpoint-info` updates, `use_ingress_for_relations` config, `dev` mode, secure-only check.
- Provide a clear migration document for operators.

**Non-Goals:**
- Changing the Hydra workload configuration.
- Replacing other integrations (database, login-ui, oauth, etc.).
- Supporting simultaneous Traefik and Istio ingress.

## Decisions

### Decision 1: Use `IstioIngressRouteRequirer.on.ready` for event handling

**Chosen:** Observe `on.ready` on the requirer (emitted on `relation_changed` and `relation_broken`). Remove the `relation_joined` special-case used by Traefik (which required manually setting `_relation`).

**Rationale:** The `IstioIngressRouteRequirer` handles lifecycle events internally and emits a clean `ready` event. The Traefik lib had a known bug requiring `requirer._relation = event.relation` workaround; the new lib does not.

**Alternative considered:** Continue using raw `relation_changed`/`relation_joined` events. Rejected because the new library's events are the correct abstraction level.

### Decision 2: Consolidate paths into single HTTPRoute per backend

**Chosen:** For the `public-route`, use a **single `HTTPRoute`** with multiple `HTTPRouteMatch` entries for all 5 paths (1 PathPrefix + 4 Exact). For the `internal-route`, use **two `HTTPRoute` objects**: one for the admin backend (4 PathPrefix matches) and one for the public backend (1 PathPrefix + 1 Exact).

**Rationale:** The `istio-ingress-route` interface supports multiple matches per route, allowing consolidation. This reduces the number of Kubernetes objects created by the provider.

**Alternative considered:** One HTTPRoute per path (mirroring the Traefik approach). Rejected as unnecessarily verbose.

### Decision 3: Remove Jinja2 templates

**Chosen:** Delete `templates/public-route.json.j2` and `templates/internal-route.json.j2`. The new config is built programmatically via typed Pydantic models.

**Rationale:** The templates were only needed for Traefik JSON config. The new interface uses Python objects, making templates obsolete and removing a source of JSON serialization bugs.

### Decision 4: Map `scheme` → TLS detection via `tls_enabled`

**Chosen:** The `IstioIngressRouteRequirer.tls_enabled` property replaces the Traefik `scheme` field. `PublicRouteData.secured` becomes `tls_enabled`. URL scheme is inferred: `https` if `tls_enabled`, `http` otherwise.

**Rationale:** Direct 1:1 semantic mapping. The old code did `scheme` → `URL(f"{scheme}://...")`, the new code does `tls_enabled` → `scheme = "https" if tls_enabled else "http"`.

### Decision 5: `submit_config` in holistic handler; ready events delegate to holistic handler + endpoint update

**Chosen:**
- `submit_config()` for both public and internal routes is called inside `_holistic_handler`, guarded by `self.unit.is_leader()` and the respective `is_ready()` check.
- The `_on_public_route_ready` and `_on_internal_ingress_ready` event handlers call `_holistic_handler` (which submits the config) and then call `_update_hydra_endpoints`.

**Rationale:** Calling `submit_config` in the holistic handler ensures the routing config is (re-)submitted on every relevant charm event (config changes, pebble ready, secret changes, etc.), not only when the ingress relation itself changes. This makes the charm self-healing: if the istio-ingress provider restarts and loses state, the next holistic run resubmits the config without requiring a new ingress relation event. The ready-event handlers stay thin: they delegate to the holistic handler and update the endpoint databag.

### Decision 6: Listener port is the ingress gateway port, not the backend service port

**Chosen:** `Listener.port` is set to the ingress gateway's external port (`443` if `tls_enabled`, `80` otherwise). `BackendRef.port` carries the internal service port (`PUBLIC_PORT=4444` or `ADMIN_PORT=4445`). Both public and internal HTTPRoutes for `InternalIngressData` bind to the **same single listener**.

**Rationale:** `Listener` maps to a Kubernetes Gateway API `Gateway.spec.listeners[]` entry. The `port` field is the external port the Gateway opens. Having `Listener(port=4445)` would instruct istio-ingress to open port 4445 externally — which is wrong and potentially a security issue. The distinction between admin and public traffic is expressed via `HTTPRouteMatch.path` + `BackendRef.port`, not via separate listeners. The ingress port follows TLS availability: `443` when `tls_enabled=True` (set by istio-ingress after cert negotiation), `80` otherwise. Because `submit_config` is called eagerly in `_holistic_handler` and again on `on.ready`, the listener port self-corrects through the natural submit→ready→re-submit cycle.

**Alternative considered:** One `Listener` per backend port (4444/4445). Rejected because it exposes internal service ports externally via the Gateway, which is architecturally incorrect.

## Risks / Trade-offs

- **Breaking change for operators**: Operators must remove the Traefik integration before upgrading and re-add with Istio after. Documented in migration guide.
  → Mitigation: Migration document in `migration/traefik-to-istio-ingress.md`.

- **`charmcraft.yaml` interface change**: The `public-route` and `internal-route` interfaces must change from `traefik_route` to `istio_ingress_route`. This is a metadata change that requires operator action.
  → Mitigation: Clearly documented in migration guide and proposal.

- **Removal of `traefik_k8s` lib**: Any charm consuming the vendored library from this charm's `lib/` will break.
  → Mitigation: The lib is not intended to be consumed; this is internal.

## Migration Plan

1. Operator removes existing `public-route` and `internal-route` Traefik relations.
2. Operator upgrades the `hydra` charm to the new version.
3. Operator relates the charm to `istio-ingress-k8s` using the same relation names.

Rollback: Deploy the previous charm revision and re-relate to Traefik.

See `migration/traefik-to-istio-ingress.md` for step-by-step instructions.

## Open Questions

- None. The `istio-ingress-route` interface is stable at `1.0.2`.
