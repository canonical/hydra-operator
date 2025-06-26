# Charmed Ory Hydra

[![CharmHub Badge](https://charmhub.io/hydra/badge.svg)](https://charmhub.io/hydra)
[![Juju](https://img.shields.io/badge/Juju%20-3.0+-%23E95420)](https://github.com/juju/juju)
[![License](https://img.shields.io/github/license/canonical/hydra-operator?label=License)](https://github.com/canonical/hydra-operator/blob/main/LICENSE)

[![Continuous Integration Status](https://github.com/canonical/hydra-operator/actions/workflows/on_push.yaml/badge.svg?branch=main)](https://github.com/canonical/hydra-operator/actions?query=branch%3Amain)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-%23FE5196.svg)](https://conventionalcommits.org)

## Description

Python Operator for Ory Hydra - a scalable, security first OAuth 2.0 and
OpenID Connect server. For more details and documentation,
visit <https://www.ory.sh/docs/hydra/>.

## Usage

```shell
juju deploy postgresql-k8s --channel 14/stable --trust
juju deploy self-signed-certificates --channel latest/stable --trust
juju deploy identity-platform-login-ui-operator --channel latest/edge --trust
juju deploy traefik-k8s --channel latest/stable --trust

juju deploy hydra --trust

juju integrate postgresql-k8s hydra
juju integrate identity-platform-login-ui-operator hydra
juju integrate traefik-k8s:certificates self-signed-certificates:certificates
juju integrate traefik-k8s hydra:public-ingress
```

You can follow the deployment status with `watch -c juju status --color`.

## Integrations

### PostgreSQL

This charm requires an integration
with [postgresql-k8s-operator](https://github.com/canonical/postgresql-k8s-operator).

### Ingress

The Hydra Operator offers integration with
the [traefik-k8s-operator](https://github.com/canonical/traefik-k8s-operator)
for ingress. Hydra has two APIs which can be exposed through ingress, the public
API and the admin API.

If you have traefik deployed and configured in your hydra model, to provide
ingress to the admin API run:

```shell
juju integrate traefik-admin hydra:admin-ingress
```

To provide ingress to the public API run:

```shell
juju integrate traefik-public hydra:public-ingress
```

Note that the public ingress needs to be secured with HTTPS if the charm
config `dev` is not `true`.

### Kratos

This charm offers integration
with [kratos-operator](https://github.com/canonical/kratos-operator). In order
to integrate hydra with kratos, it needs to be able to access hydra's admin API
endpoint. To enable that, integrate the two charms:

```shell
juju integrate kratos hydra
```

### Identity Platform Login UI

The following instructions assume that you have deployed `traefik-admin`
and `traefik-public` charms and integrated them with hydra. Note that the UI
charm should run behind a proxy.

This charm offers integration
with [identity-platform-login-ui-operator](https://github.com/canonical/identity-platform-login-ui-operator).
In order to integrate them, run:

```shell
juju integrate hydra:ui-endpoint-info identity-platform-login-ui-operator:ui-endpoint-info
juju integrate identity-platform-login-ui-operator:hydra-endpoint-info hydra:hydra-endpoint-info
```

## OCI Images

The image used by this charm is hosted
on [Docker Hub](https://hub.docker.com/r/oryd/hydra) and maintained by Ory.

## Security

Please see [SECURITY.md](https://github.com/canonical/hydra-operator/blob/main/SECURITY.md)
for guidelines on reporting security issues.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on
enhancements to this charm following best practice guidelines,
and [CONTRIBUTING.md](https://github.com/canonical/hydra-operator/blob/main/CONTRIBUTING.md)
for developer guidance.

## License

The Charmed Hydra Operator is free software, distributed under the Apache
Software License, version 2.0.
See [LICENSE](https://github.com/canonical/hydra-operator/blob/main/LICENSE) for
more information.
