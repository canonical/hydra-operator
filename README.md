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
# Deploy required charms
juju deploy postgresql-k8s --channel edge --trust
juju deploy istio-ingresss-k8s public-ingress --channel latest/edge --trust

# Deploy hydra
juju deploy hydra --trust

# Integrate with required charms
juju integrate hydra postgresql-k8s
juju integrate hydra:public-ingress public-ingress
```

You can follow the deployment status with `watch -c juju status --color`.

## Integrations

### PostgreSQL

This charm requires an integration
with [postgresql-k8s-operator](https://github.com/canonical/postgresql-k8s-operator).

### Public Ingress

This charm requires a `public-ingress` integration with
the [istio-ingress-k8s](https://github.com/canonical/istio-ingress-k8s-operator)
to expose the public API.

Make sure you've deployed
the [istio-k8s](https://github.com/canonical/istio-k8s-operator) charm
beforehand.

```shell
juju deploy istio-ingress-k8s public-ingress --channel latest/edge --trust
juju integrate hydra:public-ingress public-ingress
```

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

Security issues can be reported
through [LaunchPad](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File).
Please do not file GitHub issues about security issues.

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
