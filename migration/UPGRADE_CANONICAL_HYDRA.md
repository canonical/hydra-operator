# Migrating from Canonical Hydra v2.3.0 to Hydra v25.4.0

<!-- TODO: Publish on CharmHub / readthedocs when 0.6 is released -->

This guide outlines the specific steps required to migrate an existing Charmed Hydra deployment to `0.6`, which is based on Ory Hydra **v25.4.0**.

Unlike standard upgrades, this path requires a **manual schema sanitization** step.
The Canonical Hydra fork introduced custom database tables and columns for Device Flow support.
While Ory Hydra v25.4.0 successfully adopts most of the shared schema elements during migration, it leaves behind specific Canonical-only tables and columns that are no longer used.

This guide ensures a clean transition by applying the upstream migrations first, and then manually removing the obsolete tables and columns.

## Prerequisites

* Access to the Juju controller and Kubernetes cluster with an Identity Platform deployment

## Recommended strategy

**Strategy Overview:**
- **Blue (Current):** Charmed Hydra `0.5` with Canonical Hydra v2.3.0 connected to the production database.
- **Green (New):** Charmed Hydra upgraded to `0.6` with Ory Hydra v25.4.0 connected to a *cloned* and *sanitized* database.
- **Switchover:** Traffic is routed to Green only after the migration is verified.

1. Prepare and deploy a model with new Charmed Hydra of the **SAME REVISION** as the one you are currently using and a Charmed PostgreSQL. Integrate the two charms and enable `uuid` plugin in postgres in both models:

```shell
juju deploy hydra <new-hydra-app-name> --channel 0.5/edge --revision <original-rev>
juju deploy postgresql <new-postgresql-app-name> --channel 14/stable
juju integrate <new-hydra-app-name> <new-postgresql-app-name>

juju config <new-postgresql-app-name> plugin_uuid_ossp_enable=true
```

2. Use database migration systems or database replication mechanisms to sync source database to target database. Wait till the target database is synchronized with the source database.

3. Stop writing to the source database by blocking traffic. Wait for all remaining data to drain to the target database. The source and target databases are now fully synchronized.

**IMPORTANT: Make sure to back up your database.**

4. Upgrade the new Charmed Hydra.

```shell
juju refresh <new-hydra-app-name> --channel 0.6/edge --revision <new-rev>
```

5. Trigger the migration action. Note: depending on the data size, you may want to use a large timeout threshold.

```shell
juju run <new-hydra-app-name>/<leader> run-migration timeout=<timeout-in-seconds>
```

6. Verify that the migration was successful.

7. Sanitize the database.

**We recommend performing this step to ensure that the database schemas are cleaned up.**

First transfer the script `cleanup_canonical_hydra.sql` to the new postgresql charm:

```shell
juju scp --container postgresql cleanup_canonical_hydra.sql <new-postgresql-app-name>/leader:/tmp/cleanup_canonical_hydra.sql
```

Then execute the script against the hydra database:

```shell
psql --host <psql-host> --username=<hydra-user> --dbname=<hydra-database-name> -f /tmp/cleanup_canonical_hydra.sql
```

8. Switch over the traffic to the new Hydra Charm.
