# Contributing

## Overview

This document explains the processes and practices recommended for contributing
enhancements to this operator.

- Generally, before developing bugs or enhancements to this charm, you
  should [open an issue](https://github.com/canonical/hydra-operator/issues)
  explaining your use case.
- If you would like to chat with us about charm development, you can reach
  us
  at [Canonical Mattermost public channel](https://chat.charmhub.io/charmhub/channels/charm-dev)
  or [Discourse](https://discourse.charmhub.io/).
- Familiarising yourself with
  the [Charmed Operator Framework](https://juju.is/docs/sdk) library
  will help you a lot when working on new features or bug fixes.
- All enhancements require review before being merged. Code review typically
  examines
  - code quality
  - test coverage
  - user experience for Juju administrators of this charm.
- Please help us out in ensuring easy to review branches by rebasing your pull
  request branch onto the `main` branch. This also avoids merge commits and
  creates a linear Git commit history.

## Developing

You can use the environments created by `tox` for development. It helps
install `pre-commit` and `mypy` type checker.

```shell
tox -e dev
source .tox/dev/bin/activate
```

## Testing

```shell
tox -e unit          # unit tests
tox -e integration   # integration tests
```

To test this charm manually, execute the container:

```shell
kubectl exec -it hydra-0 -c hydra -n <model> -- sh
```

Create an exemplary client:

```shell
$ hydra create client --endpoint http://127.0.0.1:4445/ --name example-client

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
$ hydra list clients --endpoint http://127.0.0.1:4445/

CLIENT ID				CLIENT SECRET	GRANT TYPES		RESPONSE TYPES	SCOPE				AUDIENCE	REDIRECT URIS
b55b6857-968e-4fb7-be77-f701ec751405			authorization_code	code		offline_access offline openid

NEXT PAGE TOKEN
IS LAST PAGE				true
```

## Building

Build the charm in this git repository using:

```shell
charmcraft pack
```

## Deploying

```shell
# Create a model
juju add-model dev
# Enable DEBUG logging
juju model-config logging-config="<root>=INFO;unit=DEBUG"
# Deploy postgresql-k8s charm
juju deploy postgresql-k8s --channel edge --trust
# Deploy the charm
juju deploy ./hydra*.charm --resource oci-image=$(yq eval '.resources.oci-image.upstream-source' metadata.yaml)
# Add integration
juju integrate postgresql-k8s hydra
```

## Canonical Contributor Agreement

Canonical welcomes contributions to Charmed Ory Hydra. Please check out
our [contributor agreement](https://ubuntu.com/legal/contributors) if you're
interested in contributing to the solution.
