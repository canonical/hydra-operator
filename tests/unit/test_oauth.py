# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from dataclasses import replace
from unittest.mock import call, patch

from ops.testing import Context, PeerRelation, Relation, Secret
from unit.conftest import create_state

from cli import OAuthClient
from configs import ConfigFile
from constants import OAUTH_INTEGRATION_NAME
from exceptions import ClientDoesNotExistError, CommandExecError


class TestOAuthClientReconciliation:
    """Tests for the reconciliation of the `oauth` integrations with the Hydra clients."""

    def test_client_created_on_update_status_without_any_oauth_event(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        oauth_relation_ready: Relation,
    ) -> None:
        """A client is created from a holistic event even if no oauth event ever fired."""
        state = create_state(
            leader=True,
            relations=[
                peer_relation_ready,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
                oauth_relation_ready,
            ],
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch(
                "charm.CommandLine.create_oauth_client",
                return_value=OAuthClient(client_id="client_id", client_secret="client_secret"),
            ) as create_oauth_client,
            patch(
                "charm.OAuthProvider.set_client_credentials_in_relation_data"
            ) as set_credentials,
        ):
            state_out = context.run(context.on.update_status(), state)

        create_oauth_client.assert_called_once()
        peer_out = state_out.get_relation(peer_relation_ready.id)
        assert f"oauth_{oauth_relation_ready.id}" in peer_out.local_app_data
        assert set_credentials.call_args == call(
            oauth_relation_ready.id, "client_id", "client_secret"
        )

    def test_client_updated_when_requirer_redirect_uri_changes(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        oauth_relation_ready: Relation,
    ) -> None:
        """A requirer changing its redirect uri is propagated to the registered client."""
        oauth_relation = replace(
            oauth_relation_ready,
            remote_app_data={
                **oauth_relation_ready.remote_app_data,
                "redirect_uri": "https://new.example.com/callback",
            },
        )
        peer_relation = replace(
            peer_relation_ready,
            local_app_data={
                **peer_relation_ready.local_app_data,
                f"oauth_{oauth_relation.id}": json.dumps({
                    "client_id": "client_id",
                    "config_hash": "stale",
                }),
            },
        )
        state = create_state(
            leader=True,
            relations=[
                peer_relation,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
                oauth_relation,
            ],
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch(
                "charm.CommandLine.update_oauth_client",
                return_value=OAuthClient(client_id="client_id"),
            ) as update_oauth_client,
            patch("charm.CommandLine.create_oauth_client") as create_oauth_client,
        ):
            state_out = context.run(context.on.relation_changed(oauth_relation), state)

        update_oauth_client.assert_called_once()
        target = update_oauth_client.call_args.args[0]
        assert target.redirect_uris == ["https://new.example.com/callback"]
        assert target.client_id == "client_id"
        create_oauth_client.assert_not_called()

        peer_out = state_out.get_relation(peer_relation.id)
        record = json.loads(peer_out.local_app_data[f"oauth_{oauth_relation.id}"])
        assert record["client_id"] == "client_id"
        assert record["config_hash"] != "stale"

    def test_legacy_peer_record_without_config_hash_is_updated_once(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        oauth_relation_ready: Relation,
    ) -> None:
        """A pre-upgrade peer record with no config hash triggers one self-healing update.

        The upgrade must not disturb the requirer: the client is updated in place, so its id
        stays put and no credentials are republished.
        """
        peer_relation = replace(
            peer_relation_ready,
            local_app_data={
                **peer_relation_ready.local_app_data,
                f"oauth_{oauth_relation_ready.id}": json.dumps({"client_id": "client_id"}),
            },
        )
        state = create_state(
            leader=True,
            relations=[
                peer_relation,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
                oauth_relation_ready,
            ],
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            # Keep the container plan untouched so `state_out` can be fed back in.
            patch("charm.PebbleService.plan"),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch(
                "charm.CommandLine.update_oauth_client",
                return_value=OAuthClient(client_id="client_id"),
            ) as update_oauth_client,
            patch("charm.CommandLine.create_oauth_client") as create_oauth_client,
            patch(
                "charm.OAuthProvider.set_client_credentials_in_relation_data"
            ) as set_credentials,
        ):
            state_out = context.run(context.on.update_status(), state)
            context.run(context.on.update_status(), state_out)

        update_oauth_client.assert_called_once()
        create_oauth_client.assert_not_called()
        set_credentials.assert_not_called()
        peer_out = state_out.get_relation(peer_relation.id)
        record = json.loads(peer_out.local_app_data[f"oauth_{oauth_relation_ready.id}"])
        assert record["client_id"] == "client_id"
        assert record["config_hash"]

    def test_reconcile_is_idempotent(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        oauth_relation_ready: Relation,
    ) -> None:
        """Re-running the reconciliation with unchanged requirer data is a no-op."""
        state = create_state(
            leader=True,
            relations=[
                peer_relation_ready,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
                oauth_relation_ready,
            ],
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            # Keep the container plan untouched so `state_out` can be fed back in.
            patch("charm.PebbleService.plan"),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch(
                "charm.CommandLine.create_oauth_client",
                return_value=OAuthClient(client_id="client_id", client_secret="client_secret"),
            ) as create_oauth_client,
            patch("charm.CommandLine.update_oauth_client") as update_oauth_client,
            patch("charm.OAuthProvider.set_client_credentials_in_relation_data"),
        ):
            state_out = context.run(context.on.update_status(), state)
            context.run(context.on.update_status(), state_out)

        create_oauth_client.assert_called_once()
        update_oauth_client.assert_not_called()

    def test_skips_when_service_not_running(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        oauth_relation_ready: Relation,
    ) -> None:
        """No client is registered while the Hydra service is down."""
        state = create_state(
            leader=True,
            relations=[
                peer_relation_ready,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
                oauth_relation_ready,
            ],
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.WorkloadService.is_running", return_value=False),
            patch("charm.CommandLine.create_oauth_client") as create_oauth_client,
        ):
            state_out = context.run(context.on.update_status(), state)

        create_oauth_client.assert_not_called()
        peer_out = state_out.get_relation(peer_relation_ready.id)
        assert not [key for key in peer_out.local_app_data if key.startswith("oauth_")]

    def test_skips_when_peer_integration_missing(
        self,
        context: Context,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        oauth_relation_ready: Relation,
    ) -> None:
        """No client is registered while there is nowhere to record its id."""
        state = create_state(
            leader=True,
            relations=[
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
                oauth_relation_ready,
            ],
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch("charm.CommandLine.create_oauth_client") as create_oauth_client,
        ):
            context.run(context.on.update_status(), state)

        create_oauth_client.assert_not_called()

    def test_skips_relation_with_invalid_requirer_data(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        oauth_relation_ready: Relation,
    ) -> None:
        """An incomplete requirer databag does not block the other integrations."""
        invalid_relation = Relation(
            OAUTH_INTEGRATION_NAME,
            remote_app_data={
                "redirect_uri": "https://x/cb",
                "grant_types": json.dumps(["authorization_code"]),
            },
        )
        state = create_state(
            leader=True,
            relations=[
                peer_relation_ready,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
                oauth_relation_ready,
                invalid_relation,
            ],
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch(
                "charm.CommandLine.create_oauth_client",
                return_value=OAuthClient(client_id="client_id", client_secret="client_secret"),
            ) as create_oauth_client,
            patch("charm.OAuthProvider.set_client_credentials_in_relation_data"),
        ):
            state_out = context.run(context.on.update_status(), state)

        create_oauth_client.assert_called_once()
        peer_out = state_out.get_relation(peer_relation_ready.id)
        assert [key for key in peer_out.local_app_data if key.startswith("oauth_")] == [
            f"oauth_{oauth_relation_ready.id}"
        ]

    def test_garbage_collect_keeps_record_when_delete_fails(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
    ) -> None:
        """A failed deletion retains the peer record so a later run retries it."""
        peer_relation = replace(
            peer_relation_ready,
            local_app_data={
                **peer_relation_ready.local_app_data,
                "oauth_404": json.dumps({"client_id": "gone"}),
            },
        )
        state = create_state(
            leader=True,
            relations=[
                peer_relation,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
            ],
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch(
                "charm.CommandLine.delete_oauth_client",
                side_effect=CommandExecError([], 1, "", "error"),
            ) as delete_oauth_client,
            patch("charm.OAuthProvider.remove_secret") as remove_secret,
        ):
            state_out = context.run(context.on.update_status(), state)

        delete_oauth_client.assert_called_once_with("gone")
        remove_secret.assert_not_called()
        peer_out = state_out.get_relation(peer_relation.id)
        assert "oauth_404" in peer_out.local_app_data

    def test_garbage_collect_drops_record_when_client_already_gone(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
    ) -> None:
        """A client Hydra no longer knows about still releases its peer record and secret."""
        peer_relation = replace(
            peer_relation_ready,
            local_app_data={
                **peer_relation_ready.local_app_data,
                "oauth_404": json.dumps({"client_id": "gone"}),
            },
        )
        state = create_state(
            leader=True,
            relations=[
                peer_relation,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
            ],
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch(
                "charm.CommandLine.delete_oauth_client",
                side_effect=ClientDoesNotExistError,
            ),
            patch("charm.OAuthProvider.remove_secret") as remove_secret,
        ):
            state_out = context.run(context.on.update_status(), state)

        remove_secret.assert_called_once()
        peer_out = state_out.get_relation(peer_relation.id)
        assert "oauth_404" not in peer_out.local_app_data

    def test_garbage_collect_drops_record_holding_no_client_id(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
    ) -> None:
        """A peer record that is not a client mapping is discarded, not raised on."""
        peer_relation = replace(
            peer_relation_ready,
            local_app_data={
                **peer_relation_ready.local_app_data,
                "oauth_404": json.dumps("done"),
            },
        )
        state = create_state(
            leader=True,
            relations=[
                peer_relation,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
            ],
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch("charm.CommandLine.delete_oauth_client") as delete_oauth_client,
        ):
            state_out = context.run(context.on.update_status(), state)

        delete_oauth_client.assert_not_called()
        peer_out = state_out.get_relation(peer_relation.id)
        assert "oauth_404" not in peer_out.local_app_data

    def test_failed_create_writes_no_peer_record(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        oauth_relation_ready: Relation,
    ) -> None:
        """A failed creation must leave no record, or the next pass would update a ghost."""
        state = create_state(
            leader=True,
            relations=[
                peer_relation_ready,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
                oauth_relation_ready,
            ],
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch("charm.CommandLine.create_oauth_client", return_value=None),
            patch(
                "charm.OAuthProvider.set_client_credentials_in_relation_data"
            ) as set_credentials,
        ):
            state_out = context.run(context.on.update_status(), state)

        set_credentials.assert_not_called()
        peer_out = state_out.get_relation(peer_relation_ready.id)
        assert not [key for key in peer_out.local_app_data if key.startswith("oauth_")]

    def test_failed_update_keeps_the_stale_fingerprint(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        oauth_relation_ready: Relation,
    ) -> None:
        """Recording the new hash after a failed update would mask the drift forever."""
        peer_relation = replace(
            peer_relation_ready,
            local_app_data={
                **peer_relation_ready.local_app_data,
                f"oauth_{oauth_relation_ready.id}": json.dumps({
                    "client_id": "client_id",
                    "config_hash": "stale",
                }),
            },
        )
        state = create_state(
            leader=True,
            relations=[
                peer_relation,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
                oauth_relation_ready,
            ],
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch("charm.CommandLine.update_oauth_client", return_value=None),
            patch(
                "charm.CommandLine.get_oauth_client",
                return_value=OAuthClient(client_id="client_id"),
            ),
        ):
            state_out = context.run(context.on.update_status(), state)

        peer_out = state_out.get_relation(peer_relation.id)
        record = json.loads(peer_out.local_app_data[f"oauth_{oauth_relation_ready.id}"])
        assert record["config_hash"] == "stale"

    def test_client_recreated_when_it_vanished_from_hydra(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        oauth_relation_ready: Relation,
    ) -> None:
        """An update against a client Hydra lost falls back to registering a new one."""
        peer_relation = replace(
            peer_relation_ready,
            local_app_data={
                **peer_relation_ready.local_app_data,
                f"oauth_{oauth_relation_ready.id}": json.dumps({
                    "client_id": "vanished",
                    "config_hash": "stale",
                }),
            },
        )
        state = create_state(
            leader=True,
            relations=[
                peer_relation,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
                oauth_relation_ready,
            ],
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch("charm.CommandLine.update_oauth_client", return_value=None),
            patch(
                "charm.CommandLine.get_oauth_client",
                side_effect=ClientDoesNotExistError,
            ),
            patch(
                "charm.CommandLine.create_oauth_client",
                return_value=OAuthClient(client_id="fresh_id", client_secret="fresh_secret"),
            ) as create_oauth_client,
            patch(
                "charm.OAuthProvider.set_client_credentials_in_relation_data"
            ) as set_credentials,
        ):
            state_out = context.run(context.on.update_status(), state)

        create_oauth_client.assert_called_once()
        assert set_credentials.call_args == call(
            oauth_relation_ready.id, "fresh_id", "fresh_secret"
        )
        peer_out = state_out.get_relation(peer_relation.id)
        record = json.loads(peer_out.local_app_data[f"oauth_{oauth_relation_ready.id}"])
        assert record["client_id"] == "fresh_id"
        assert record["config_hash"] != "stale"

    def test_non_leader_never_touches_hydra(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        oauth_relation_ready: Relation,
    ) -> None:
        """Without the leader guard every unit would register its own duplicate client."""
        state = create_state(
            leader=False,
            relations=[
                peer_relation_ready,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
                oauth_relation_ready,
            ],
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch("charm.CommandLine.create_oauth_client") as create_oauth_client,
            patch("charm.CommandLine.update_oauth_client") as update_oauth_client,
            patch("charm.CommandLine.delete_oauth_client") as delete_oauth_client,
        ):
            context.run(context.on.update_status(), state)

        create_oauth_client.assert_not_called()
        update_oauth_client.assert_not_called()
        delete_oauth_client.assert_not_called()

    def test_inconclusive_existence_check_does_not_register_a_duplicate(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        oauth_relation_ready: Relation,
    ) -> None:
        """An unreachable Hydra must not be mistaken for a Hydra that lost the client."""
        peer_relation = replace(
            peer_relation_ready,
            local_app_data={
                **peer_relation_ready.local_app_data,
                f"oauth_{oauth_relation_ready.id}": json.dumps({
                    "client_id": "live_client",
                    "config_hash": "stale",
                }),
            },
        )
        state = create_state(
            leader=True,
            relations=[
                peer_relation,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
                oauth_relation_ready,
            ],
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch("charm.CommandLine.update_oauth_client", return_value=None),
            patch("charm.CommandLine.get_oauth_client", return_value=None),
            patch("charm.CommandLine.create_oauth_client") as create_oauth_client,
        ):
            state_out = context.run(context.on.update_status(), state)

        create_oauth_client.assert_not_called()
        peer_out = state_out.get_relation(peer_relation.id)
        record = json.loads(peer_out.local_app_data[f"oauth_{oauth_relation_ready.id}"])
        assert record["client_id"] == "live_client"
        assert record["config_hash"] == "stale"

    def test_one_failing_integration_does_not_discard_the_others(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        oauth_relation_ready: Relation,
    ) -> None:
        """One integration's failure must not discard the peer writes staged for the others.

        The retry would otherwise create a second Hydra client for each of them.
        """
        second = Relation(
            OAUTH_INTEGRATION_NAME, remote_app_data=oauth_relation_ready.remote_app_data
        )
        state = create_state(
            leader=True,
            relations=[
                peer_relation_ready,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
                oauth_relation_ready,
                second,
            ],
        )

        def explode_for_the_first(relation_id: int, *_: str) -> None:
            if relation_id == oauth_relation_ready.id:
                raise RuntimeError("secret backend is unhappy")

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch(
                "charm.CommandLine.create_oauth_client",
                return_value=OAuthClient(client_id="client_id", client_secret="client_secret"),
            ),
            patch(
                "charm.OAuthProvider.set_client_credentials_in_relation_data",
                side_effect=explode_for_the_first,
            ),
        ):
            state_out = context.run(context.on.update_status(), state)

        peer_out = state_out.get_relation(peer_relation_ready.id)
        assert f"oauth_{second.id}" in peer_out.local_app_data
        assert f"oauth_{oauth_relation_ready.id}" not in peer_out.local_app_data

    def test_peer_record_without_a_client_id_is_skipped(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        oauth_relation_ready: Relation,
    ) -> None:
        """A corrupt record blocks the integration, so Hydra must not be touched for it."""
        peer_relation = replace(
            peer_relation_ready,
            local_app_data={
                **peer_relation_ready.local_app_data,
                f"oauth_{oauth_relation_ready.id}": json.dumps({"config_hash": "x"}),
            },
        )
        state = create_state(
            leader=True,
            relations=[
                peer_relation,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
                oauth_relation_ready,
            ],
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch("charm.CommandLine.create_oauth_client") as create_oauth_client,
            patch("charm.CommandLine.update_oauth_client") as update_oauth_client,
        ):
            context.run(context.on.update_status(), state)

        create_oauth_client.assert_not_called()
        update_oauth_client.assert_not_called()

    def test_reordered_requirer_lists_do_not_trigger_an_update(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        oauth_relation_ready: Relation,
    ) -> None:
        """List order carries no meaning to Hydra, and an unstable hash would loop."""
        grant_types = ["authorization_code", "refresh_token"]
        relations = [
            peer_relation_ready,
            db_relation_ready,
            public_route_relation_ready,
            login_ui_relation_ready,
        ]
        hashes = []
        for order in (grant_types, list(reversed(grant_types))):
            oauth_relation = replace(
                oauth_relation_ready,
                remote_app_data={
                    **oauth_relation_ready.remote_app_data,
                    "grant_types": json.dumps(order),
                },
            )
            state = create_state(leader=True, relations=[*relations, oauth_relation])
            with (
                patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
                patch("charm.NOOP_CONDITIONS", new=[]),
                patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
                patch("charm.WorkloadService.is_running", return_value=True),
                patch(
                    "charm.CommandLine.create_oauth_client",
                    return_value=OAuthClient(client_id="client_id", client_secret="secret"),
                ),
                patch("charm.OAuthProvider.set_client_credentials_in_relation_data"),
            ):
                state_out = context.run(context.on.update_status(), state)
            peer_out = state_out.get_relation(peer_relation_ready.id)
            record = json.loads(peer_out.local_app_data[f"oauth_{oauth_relation.id}"])
            hashes.append(record["config_hash"])

        assert hashes[0] == hashes[1]

    def test_recreated_client_keeps_the_secret_the_requirer_holds(
        self,
        context: Context,
        peer_relation_ready: PeerRelation,
        db_relation_ready: Relation,
        public_route_relation_ready: Relation,
        login_ui_relation_ready: Relation,
        oauth_relation_ready: Relation,
    ) -> None:
        """A new secret revision would leave the requirer on the revision it still tracks."""
        peer_relation = replace(
            peer_relation_ready,
            local_app_data={
                **peer_relation_ready.local_app_data,
                f"oauth_{oauth_relation_ready.id}": json.dumps({
                    "client_id": "vanished",
                    "config_hash": "stale",
                }),
            },
        )
        client_secret = Secret(
            owner="app",
            label=f"client_secret_{oauth_relation_ready.id}",
            tracked_content={"secret": "the-requirer-has-this"},
        )
        state = create_state(
            leader=True,
            relations=[
                peer_relation,
                db_relation_ready,
                public_route_relation_ready,
                login_ui_relation_ready,
                oauth_relation_ready,
            ],
            secrets=[client_secret],
        )

        with (
            patch("charm.ConfigFile.from_sources", return_value=ConfigFile("config")),
            patch("charm.NOOP_CONDITIONS", new=[]),
            patch("charm.EVENT_DEFER_CONDITIONS", new=[]),
            patch("charm.WorkloadService.is_running", return_value=True),
            patch("charm.CommandLine.update_oauth_client", return_value=None),
            patch(
                "charm.CommandLine.get_oauth_client",
                side_effect=ClientDoesNotExistError,
            ),
            patch(
                "charm.CommandLine.create_oauth_client",
                return_value=OAuthClient(client_id="fresh", client_secret="the-requirer-has-this"),
            ) as create_oauth_client,
        ):
            context.run(context.on.update_status(), state)

        target = create_oauth_client.call_args.args[0]
        assert target.client_secret == "the-requirer-has-this"
