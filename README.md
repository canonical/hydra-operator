# Charmed Ory Hydra

[![CharmHub Badge](https://charmhub.io/hydra/badge.svg)](https://charmhub.io/hydra)

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

### Kratos

This charm offers integration with [kratos-operator](https://github.com/canonical/kratos-operator). In order to integrate hydra with kratos, it needs to be able to access hydra's admin API endpoint.
To enable that, integrate the two charms:
```console
juju integrate kratos hydra
```

### Identity Platform Login UI

The following instructions assume that you have deployed `traefik-admin` and `traefik-public` charms and related them to hydra. Note that the UI charm should run behind a proxy.

This charm offers integration with [identity-platform-login-ui-operator](https://github.com/canonical/identity-platform-login-ui-operator). In order to integrate them, run:

```console
juju integrate hydra:ui-endpoint-info identity-platform-login-ui-operator:ui-endpoint-info
juju integrate identity-platform-login-ui-operator:hydra-endpoint-info hydra:hydra-endpoint-info
```

## OCI Images

The image used by this charm is hosted on [Docker Hub](https://hub.docker.com/r/oryd/hydra) and maintained by Ory.

## Security

Security issues can be reported through [LaunchPad](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File). Please do not file GitHub issues about security issues.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this
charm following best practice guidelines, and
[CONTRIBUTING.md](https://github.com/canonical/hydra-operator/blob/main/CONTRIBUTING.md) for developer guidance.

## License

The Charmed Hydra Operator is free software, distributed under the Apache Software License, version 2.0. See [LICENSE](https://github.com/canonical/hydra-operator/blob/main/LICENSE) for more information.
