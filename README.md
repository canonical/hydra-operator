# Charmed Ory Hydra

## Description

Python Operator for Ory Hydra - a scalable, security first OAuth 2.0 and OpenID Connect server. For more details and documentation, visit https://www.ory.sh/docs/hydra/

## Usage

```bash
juju deploy postgresql-k8s --channel edge --trust
juju deploy hydra --trust
juju relate postgresql-k8s hydra
```

You can follow the deployment status with `watch -c juju status --color`.

## Relations

### PostgreSQL

This charm requires a relation with [postgresql-k8s-operator](https://github.com/canonical/postgresql-k8s-operator).

### Ingress

The Hydra Operator offers integration with the [traefik-k8s-operator](https://github.com/canonical/traefik-k8s-operator) for ingress. Hydra has two APIs which can be exposed through ingress, the public API and the admin API.

If you have traefik deployed and configured in your hydra model, to provide ingress to the admin API run:

```bash
juju relate traefik-admin hydra:admin-ingress
```

To provide ingress to the public API run:

```bash
juju relate traefik-public hydra:public-ingress
```

## OCI Images

The image used by this charm is hosted on [Docker Hub](https://hub.docker.com/r/oryd/hydra) and maintained by Ory.
