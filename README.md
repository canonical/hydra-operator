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

## Run Hydra from backup

When migrating an Ory Hydra instance—for example, to a new server or environment—you need to ensure the new instance can decrypt existing user sessions and data. Hydra relies on two crucial secrets for this:

1. System Secret: Used to encrypt sensitive data stored in the database, such as session payloads and JSON Web Key Sets (JWKS).
2. Cookie Secret: Used to encrypt and sign Hydra's cookies.

If you restore Hydra from a database backup without using the original secrets, the new instance will generate its own, rendering the backed-up data unusable. The Charmed Hydra Operator provides several helper actions and configuration options to manage these secrets and enable seamless server migration.

### Key Management Actions

The operator includes two Juju actions for managing secrets on a running Hydra instance.

#### get-secret-keys

This action retrieves the current secret keys used by Hydra. It's essential for backing up secrets before a migration.

```console
# Get the system secret keys
juju run hydra/0 get-secret-keys type=system

# Get the cookie secret keys
juju run hydra/0 get-secret-keys type=cookie
```

#### add-secret-key

This action adds a new secret key to Hydra's configuration. This is useful for key rotation or for adding a key from a backup to an existing deployment.

```console
juju run hydra/0 add-secret-key type=cookie key=YOUR_NEW_COOKIE_SECRET
```

NOTE: key length MUST be >16 characters

### Config

When deploying a new Hydra instance, you can use the following Juju configuration options to pre-seed the secrets, preventing the charm from generating new ones. These configurations only work on the initial deployment.

- `initial_system_secret_id`: The ID of a Juju secret containing the system keys.
- `initial_cookie_secret_id`: The ID of a Juju secret containing the cookie keys.

These config have no effect after the charm has been deployed and secrets have been generated.

### Migration Walkthrough

Let's walk through a common server migration scenario. Assume you have an existing Hydra deployment (old-model) integrated with a PostgreSQL database, and you want to migrate it to a new Juju model (new-model).

First we need to get the old Hydra secret keys:

```console
$ juju run -m old-model hydra/0 get-secret-keys type=system -q
system: '["old-system-key-1", "old-system-key-2"]'

$ juju run -m old-model hydra/0 get-secret-keys type=cookie -q
cookie: '["old-cookie-key-1", "old-cookie-key-2"]'
```

In your new model, create Juju secrets using the values you just retrieved:

```console
$ juju add-secret -m new-model hydra-system-keys system1=old-system-key-1 system2=old-system-key-2

$ juju add-secret -m new-model hydra-cookie-keys cookie1=old-cookie-key-1 cookie2=old-cookie-key-2
```

💡 Important: The order of the key-value pairs matters. The first key you provide (e.g., system1) will become the primary secret for the new Hydra instance.

Now we can deploy the Hydra in the new model, referencing the Juju secrets you just created:

```console
juju deploy -m new-model hydra --config initial_system_secret_id=secret:<system-secret-id> --config initial_cookie_secret_id=secret:<cookie-secret-id>
```

After deployment, you must grant the Hydra charm access to the secrets:

```console
juju grant-secret -m new-model system hydra
juju grant-secret -m new-model cookie hydra
```

Now, integrate the new Hydra instance with your migrated PostgreSQL database and any other necessary applications:

```console
juju integrate -m new-model hydra postgresql
# ... integrate with other applications as needed
```

Once the new Hydra instance is running and integrated, it should be able to decrypt and use the backed-up database data seamlessly. You can verify this by checking that the new instance's JWKS endpoint (https://hydra-url/.well-known/jwks.json) matches the one from your old deployment.

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
