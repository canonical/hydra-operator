# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""A helper class for interacting with the hydra CLI."""


import json
import logging
from typing import Dict, List, Optional, Tuple, Union

from charms.hydra.v0.oauth import ClientConfig
from ops.model import Container

logger = logging.getLogger(__name__)



class HydraCLI:
    """Helper object for running hydra CLI commands."""

    def __init__(self, hydra_admin_url: str, container: Container):
        self.hydra_admin_url = hydra_admin_url
        self.container = container

    def _client_config_to_cmd(
        self, client_config: ClientConfig, metadata: Optional[Dict] = None
    ) -> List[str]:
        """Convert a ClientConfig object to a list of parameters."""
        flags = [
            "--grant-type",
            ",".join(client_config.grant_types or ["authorization_code", "refresh_token"]),
            "--response-type",
            "code",
        ]

        if client_config.scope:
            for s in client_config.scope.split(" "):
                flags.append("--scope")
                flags.append(s)
        if client_config.redirect_uri:
            flags.append("--redirect-uri")
            flags.append(client_config.redirect_uri)
        if metadata:
            flags.append("--metadata")
            flags.append(json.dumps(metadata))
        return flags

    def _client_cmd_prefix(self, action: str) -> List[str]:
        return [
            "hydra",
            action,
            "client",
            "--endpoint",
            self.hydra_admin_url,
            "--format",
            "json",
        ]

    def create_client(self, client_config: ClientConfig, metadata: Optional[Dict] = None) -> Dict:
        """Create an oauth2 client."""
        cmd = self._client_cmd_prefix("create") + self._client_config_to_cmd(
            client_config, metadata
        )

        stdout, _ = self._run_cmd(cmd)
        json_stdout = json.loads(stdout)
        logger.info(f"Successfully created client: {json_stdout.get('client_id')}")
        return json_stdout

    def update_client(self, client_config: ClientConfig, metadata: Optional[Dict] = None) -> Dict:
        """Update an oauth2 client."""
        cmd = self._client_cmd_prefix("update") + self._client_config_to_cmd(
            client_config, metadata
        )
        cmd.append(client_config.client_id)

        stdout, _ = self._run_cmd(cmd)
        logger.info(f"Successfully updated client: {client_config.client_id}")
        return json.loads(stdout)

    def delete_client(self, client_id: str) -> Dict:
        """Delete an oauth2 client."""
        cmd = self._client_cmd_prefix("delete")
        cmd.append(client_id)

        stdout, _ = self._run_cmd(cmd)
        logger.info(f"Successfully deleted client: {stdout}")
        return json.loads(stdout)

    def _run_cmd(
        self, cmd: List[str], timeout: float = 20
    ) -> Tuple[Union[str, bytes], Union[str, bytes]]:
        logger.debug(f"Running cmd: {cmd}")
        process = self.container.exec(cmd, timeout=timeout)
        stdout, stderr = process.wait_output()
        return stdout, stderr
