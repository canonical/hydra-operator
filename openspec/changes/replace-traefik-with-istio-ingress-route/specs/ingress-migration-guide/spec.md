## ADDED Requirements

### Requirement: Migration document is provided

The charm repository SHALL include a migration document at `migration/traefik-to-istio-ingress.md` that guides operators through upgrading from the Traefik-based ingress to the Istio-based ingress.

#### Scenario: Migration document exists

- **WHEN** the charm is built
- **THEN** `migration/traefik-to-istio-ingress.md` exists in the repository with steps for removing Traefik relations, upgrading, and re-adding Istio relations

### Requirement: Migration document covers rollback

The migration document SHALL include a rollback procedure that describes how to return to the previous charm revision.

#### Scenario: Rollback instructions present

- **WHEN** an operator reads the migration document
- **THEN** they can find clear instructions for rolling back to the previous Traefik-based version
