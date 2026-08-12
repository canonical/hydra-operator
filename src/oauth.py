# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Reconciliation between the `oauth` integrations and the OAuth2 clients in Hydra."""

import hashlib
import json
import logging
from typing import Any

from charms.hydra.v0.oauth import DataValidationError, OAuthProvider
from ops.model import Model, Relation

from cli import CommandLine, OAuthClient
from constants import OAUTH_INTEGRATION_NAME
from exceptions import ClientDoesNotExistError, CommandExecError
from integrations import PeerData

logger = logging.getLogger(__name__)

OAUTH_PEER_KEY_PREFIX = "oauth_"


def _fingerprint(client: OAuthClient) -> str:
    """Return a stable hash of the client configuration Hydra is expected to hold.

    The client id and secret are excluded so that the create pass and every later update
    pass hash identically, and so that no digest of a secret is ever written to the peer
    databag. List values are sorted because their order carries no meaning to Hydra and a
    requirer that derives them from a set would otherwise produce a new digest every hook.
    """
    payload = client.model_dump(
        by_alias=True, exclude_none=True, exclude={"client_id", "client_secret"}, mode="json"
    )
    canonical = {k: sorted(v) if isinstance(v, list) else v for k, v in payload.items()}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


class OAuthReconciler:
    """Synchronize the `oauth` integrations with the OAuth2 clients registered in Hydra."""

    def __init__(
        self,
        model: Model,
        peer_data: PeerData,
        oauth_provider: OAuthProvider,
        cli: CommandLine,
    ) -> None:
        self._model = model
        self._peer_data = peer_data
        self._oauth_provider = oauth_provider
        self._cli = cli

    def reconcile(self, force: bool = False) -> list[int]:
        """Create or update the Hydra OAuth2 client of every `oauth` integration.

        The requirer databag of every integration is read on every pass: drift can only be
        detected by comparing the published configuration against the recorded fingerprint,
        so the peer record cannot short-circuit the read.

        Args:
            force: reapply the configuration even when the fingerprint is unchanged. Used by
                the `reconcile-oauth-clients` action to repair clients that were changed or
                removed in Hydra behind the charm's back.

        Returns:
            The ids of the integrations whose Hydra client could not be reconciled. An
            integration whose requirer data is invalid is not among them: only the requirer
            can fix that, and the next pass picks it up once they do.
        """
        if not self._model.unit.is_leader():
            return []

        failed: list[int] = []
        for relation in self._model.relations[OAUTH_INTEGRATION_NAME]:
            try:
                if not self._reconcile_relation(relation, force):
                    failed.append(relation.id)
            except DataValidationError:
                logger.warning(
                    "The requirer data of the oauth integration %d is invalid, skipping it",
                    relation.id,
                )
            except Exception:
                # A failure here must not abort the hook: the peer records already staged for
                # the integrations reconciled earlier in this pass would be discarded, and the
                # retry would create a second Hydra client for each of them.
                logger.exception("Failed to reconcile the oauth integration %d", relation.id)
                failed.append(relation.id)

        return failed

    def garbage_collect(self) -> int:
        """Delete the OAuth2 clients whose `oauth` integration no longer exists."""
        if not self._model.unit.is_leader():
            return 0

        deleted: list[str] = []
        for key in self._peer_data.keys():
            if not key.startswith(OAUTH_PEER_KEY_PREFIX):
                continue

            relation_id = int(key[len(OAUTH_PEER_KEY_PREFIX) :])
            relation = self._model.get_relation(OAUTH_INTEGRATION_NAME, relation_id=relation_id)
            if relation is None or relation.active:
                continue

            record = self._record(relation_id)
            if not (client_id := record.get("client_id")):
                logger.warning(
                    "The peer data of the oauth integration %d holds no client id, dropping it",
                    relation_id,
                )
                deleted.append(key)
                continue

            try:
                self._cli.delete_oauth_client(client_id)
            except CommandExecError:
                logger.error(
                    "Failed to delete the OAuth client bound with the oauth integration: %d. "
                    "Please run the 'reconcile-oauth-clients' action.",
                    relation_id,
                )
                continue
            except ClientDoesNotExistError:
                pass

            self._oauth_provider.remove_secret(relation)
            deleted.append(key)

        for key in deleted:
            self._peer_data.pop(key)

        return len(deleted)

    def _peer_key(self, relation_id: int) -> str:
        return f"{OAUTH_PEER_KEY_PREFIX}{relation_id}"

    def _record(self, relation_id: int) -> dict[str, Any]:
        """Read an integration's client record, treating a malformed value as absent."""
        value = self._peer_data[self._peer_key(relation_id)]
        return value if isinstance(value, dict) else {}

    def _reconcile_relation(self, relation: Relation, force: bool) -> bool:
        if not (client_config := self._oauth_provider.get_client_config(relation)):
            logger.info(
                "The oauth integration %d has no client configuration yet, skipping it",
                relation.id,
            )
            return True

        target = OAuthClient(
            **client_config.to_dict(),
            metadata={"integration-id": str(relation.id)},
        )
        fingerprint = _fingerprint(target)
        record = self._record(relation.id)

        if not record:
            return self._create_client(relation, target, fingerprint)

        if not (client_id := record.get("client_id")):
            logger.error(
                "The peer data of the oauth integration %d holds no client id, skipping it",
                relation.id,
            )
            return False

        if record.get("config_hash") == fingerprint and not force:
            return True

        return self._update_client(relation, target, client_id, fingerprint)

    def _create_client(self, relation: Relation, target: OAuthClient, fingerprint: str) -> bool:
        if not (created := self._cli.create_oauth_client(target)):
            logger.error("Failed to create the OAuth client bound with the oauth integration")
            return False

        # Publish first: recording first would commit a fingerprint that matches for ever if
        # the publish then failed, leaving the requirer without credentials permanently.
        self._oauth_provider.set_client_credentials_in_relation_data(
            relation.id,
            created.client_id,  # type: ignore[arg-type]
            created.client_secret,  # type: ignore[arg-type]
        )
        self._peer_data[self._peer_key(relation.id)] = {
            "client_id": created.client_id,
            "config_hash": fingerprint,
        }
        return True

    def _update_client(
        self, relation: Relation, target: OAuthClient, client_id: str, fingerprint: str
    ) -> bool:
        target.client_id = client_id
        if self._cli.update_oauth_client(target):
            self._peer_data[self._peer_key(relation.id)] = {
                "client_id": client_id,
                "config_hash": fingerprint,
            }
            return True

        # Only a definite "Hydra does not have it" justifies registering a replacement; an
        # inconclusive lookup would leave the original client live and unmanaged.
        try:
            self._cli.get_oauth_client(client_id)
        except ClientDoesNotExistError:
            pass
        else:
            logger.error(
                "Failed to update the OAuth client bound with the oauth integration: %d",
                relation.id,
            )
            return False

        # The client is gone from Hydra (database restored, deleted out of band). The peer
        # record is the only trace left, so register a replacement and republish it.
        #
        # Re-register with the secret the requirer already holds. Writing a different one
        # would cut a new juju secret revision, and the requirer reads the revision it
        # tracks, so it would keep authenticating with a secret Hydra no longer accepts.
        logger.warning(
            "The OAuth client of the oauth integration %d no longer exists in Hydra, recreating it",
            relation.id,
        )
        target.client_id = None
        target.client_secret = self._oauth_provider.get_client_secret(relation)
        return self._create_client(relation, target, fingerprint)
