#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import lightkube
import pytest
import yaml
from lightkube.resources.apps_v1 import StatefulSet
from pytest_operator.plugin import OpsTest
from tenacity import Retrying, stop_after_attempt, stop_after_delay, wait_exponential

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
        trust=True,
    )

    await ops_test.model.add_relation(
        APP_NAME,
        "postgresql-k8s",
    )

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME],
            raise_on_blocked=False,
            status="active",
            timeout=1000,
        )
        assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"


@pytest.mark.abort_on_fail
def test_statefulset_readiness(ops_test: OpsTest):
    lightkube_client = lightkube.Client()
    for attempt in retry_for_5_attempts:
        logger.info(
            f"Waiting for StatefulSet replica(s) to be ready"
            f"(attempt {attempt.retry_state.attempt_number})"
        )
        with attempt:
            statefulset = lightkube_client.get(
                StatefulSet, APP_NAME, namespace=ops_test.model_name
            )

            expected_replicas = statefulset.spec.replicas
            ready_replicas = statefulset.status.readyReplicas

            assert expected_replicas == ready_replicas


# Helper to retry calling a function over 30 seconds or 5 attempts
retry_for_5_attempts = Retrying(
    stop=(stop_after_attempt(5) | stop_after_delay(30)),
    wait=wait_exponential(multiplier=1, min=5, max=10),
    reraise=True,
)
