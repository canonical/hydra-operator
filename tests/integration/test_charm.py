#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build hydra and deploy it with required charms and relations."""
    charm = await ops_test.build_charm(".")
    hydra_image_path = METADATA["resources"]["oci-image"]["upstream-source"]

    await ops_test.model.deploy(
        entity_url="postgresql-k8s",
        channel="latest/edge",
        trust=True,
    )

    await ops_test.model.deploy(
        application_name=APP_NAME,
        entity_url=charm,
        resources={"oci-image": hydra_image_path},
        series="jammy",
        trust=True,
    )

    await ops_test.model.add_relation(
        APP_NAME,
        "postgresql-k8s",
    )

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            raise_on_blocked=False,
            status="active",
            timeout=1000,
        )
        assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"
