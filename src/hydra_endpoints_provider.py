#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Provider side of the hydra-endpoints-info relation interface."""
import logging

from ops.framework import Object

logger = logging.getLogger(__name__)

RELATION_NAME = "endpoint-info"


class HydraEndpointsProvider(Object):
    """Provides endpoints information."""

    def __init__(self, charm, relation_name=RELATION_NAME):
        super().__init__(charm, relation_name)

    def send_endpoint_relation_data(self, charm, admin_endpoint, public_endpoint):
        """Updates relation with endpoints info."""
        relations = self.model.relations[RELATION_NAME]
        for relation in relations:
            relation.data[charm].update(
                {
                    "admin_endpoint": admin_endpoint,
                    "public_endpoint": public_endpoint,
                }
            )
