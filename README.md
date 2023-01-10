# Charmed Ory Hydra

## Description

This repository hosts the Kubernetes Python Operator for Ory Hydra - a scalable, security first OAuth 2.0 and OpenID Connect server.

For more details and documentation, visit https://www.ory.sh/docs/hydra/

## Usage

The Hydra Operator may be deployed using the Juju command line as follows:

Deploy the `postgresql-k8s` charm:

```bash
juju deploy postgresql-k8s --channel edge --trust
```

Clone this repository and pack the Hydra Operator with charmcraft:
```bash
charmcraft pack
```

Deploy the charm:
<!-- TODO: Update to deploy from charmhub once the charm is published -->
```bash
juju deploy ./hydra*.charm --resource oci-image=$(yq eval '.resources.oci-image.upstream-source' metadata.yaml)
```

Finally, add the required relation:
```bash
juju relate postgresql-k8s hydra
```

You can follow the deployment status with `watch -c juju status --color`.

### Ingress

The Hydra Operator offers integration with the [traefik-k8s-operator](https://github.com/canonical/traefik-k8s-operator) for ingress. Hydra has two APIs which can be exposed through ingress, the public API and the admin API.

If you have a traefik deployed and configured in your hydra model, to provide ingress to the admin API run:
```console
juju relate traefik-admin hydra:admin-ingress
```

To provide ingress to the public API run:
```console
juju relate traefik-public hydra:public-ingress
```

## Testing

Unit and integration tests can be run with tox:
```bash
tox -e unit
tox -e integration
```

To test this charm manually, execute the container:
```bash
kubectl exec -it hydra-0 -c hydra -n <model> -- sh
```

Create an exemplary client:
```shell
# hydra create client --endpoint http://127.0.0.1:4445/ --name example-client
CLIENT ID	b55b6857-968e-4fb7-be77-f701ec751405
CLIENT SECRET	b3wFYH2N_epJY6C8jCuinBRP60
GRANT TYPES	authorization_code
RESPONSE TYPES	code
SCOPE		offline_access offline openid
AUDIENCE
REDIRECT URIS
```

List the clients:
```shell
# hydra list clients --endpoint http://127.0.0.1:4445/
CLIENT ID				CLIENT SECRET	GRANT TYPES		RESPONSE TYPES	SCOPE				AUDIENCE	REDIRECT URIS
b55b6857-968e-4fb7-be77-f701ec751405			authorization_code	code		offline_access offline openid

NEXT PAGE TOKEN
IS LAST PAGE				true
```

## Relations

This charm requires a relation with [postgresql-k8s-operator](https://github.com/canonical/postgresql-k8s-operator).

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
