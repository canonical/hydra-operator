# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
import os
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ops.model import _ModelBackend

from cli import CommandLine, OAuthClient, OAuthClientPage
from constants import (
    OAUTH_CLIENT_EXPORT_CONTAINER,
    OAUTH_CLIENT_EXPORT_DIR,
    OAUTH_CLIENT_EXPORT_FILE_NAME,
    OAUTH_CLIENT_EXPORT_MAX_BYTES,
    OAUTH_CLIENT_EXPORT_TIMEOUT_SECONDS,
    OAUTH_CLIENT_INLINE_RESULT_BUDGET_BYTES,
)
from exceptions import OAuthClientListingError
from oauth_client_listing import (
    OAuthClientRetriever,
    encoded_action_results_size,
    format_action_result_args,
    serialize_oauth_client,
)


@pytest.fixture
def cli() -> MagicMock:
    return MagicMock(spec=CommandLine)


@pytest.fixture
def listing(cli: MagicMock, tmp_path: Path) -> OAuthClientRetriever:
    return OAuthClientRetriever(cli, tmp_path, "hydra/0")


class TestSerializationAndInlineListing:
    def test_serialize_oauth_client_preserves_aliases_and_excludes_none_and_secret(self) -> None:
        client = OAuthClient(
            client_id="client-1",
            client_secret="top-secret-value",
            name="My App",
            redirect_uris=["https://example.com/cb"],
            response_types=["code", "id_token"],
            scope="openid profile",
            token_endpoint_auth_method="client_secret_basic",
            grant_types=["authorization_code"],
            audience=["https://api.example.com"],
            contacts=["admin@example.com"],
            client_uri="https://example.com",
            metadata={"integration-id": "42"},
        )

        serialized = serialize_oauth_client(client)

        assert serialized == {
            "client-id": "client-1",
            "name": "My App",
            "redirect-uris": ["https://example.com/cb"],
            "response-types": ["code", "id_token"],
            "scope": ["openid", "profile"],
            "token-endpoint-auth-method": "client_secret_basic",
            "grant-types": ["authorization_code"],
            "audience": ["https://api.example.com"],
            "contacts": ["admin@example.com"],
            "client-uri": "https://example.com",
            "metadata": {"integration-id": "42"},
        }
        assert "client-secret" not in serialized
        assert "client_secret" not in serialized

    def test_serialize_oauth_client_omits_optional_none_fields(self) -> None:
        client = OAuthClient(client_id="client-minimal", client_secret="hidden-secret")

        serialized = serialize_oauth_client(client)

        assert serialized == {
            "client-id": "client-minimal",
            "redirect-uris": [],
            "response-types": ["code"],
            "scope": ["openid,profile,email,phone"],
            "metadata": {},
            "contacts": [],
        }
        assert "name" not in serialized
        assert "audience" not in serialized
        assert "grant-types" not in serialized
        assert "client-uri" not in serialized
        assert "token-endpoint-auth-method" not in serialized
        assert "client-secret" not in serialized

    def test_default_inline_listing_fetches_one_page_and_omits_absent_token(
        self, listing: OAuthClientRetriever, cli: MagicMock
    ) -> None:
        cli.list_oauth_clients.return_value = OAuthClientPage(
            items=[OAuthClient(client_id="c1", client_secret="s3cr3t")],
            next_page_token=None,
        )

        results = listing.run({})

        cli.list_oauth_clients.assert_called_once_with(page_size=100, page_token="")
        assert set(results.keys()) == {"clients"}
        parsed = json.loads(str(results["clients"]))
        assert len(parsed) == 1
        assert parsed[0]["client-id"] == "c1"
        assert "client-secret" not in parsed[0]
        assert "s3cr3t" not in str(results["clients"])

    def test_empty_inventory_succeeds_with_empty_json_array(
        self, listing: OAuthClientRetriever, cli: MagicMock
    ) -> None:
        cli.list_oauth_clients.return_value = OAuthClientPage(items=[], next_page_token=None)

        results = listing.run({})

        assert results == {"clients": "[]"}

    def test_short_or_empty_page_preserves_continuation_token(
        self, listing: OAuthClientRetriever, cli: MagicMock
    ) -> None:
        cli.list_oauth_clients.return_value = OAuthClientPage(
            items=[], next_page_token="more-pages-token"
        )

        results = listing.run({"page-size": 50, "page-token": "start-token"})

        cli.list_oauth_clients.assert_called_once_with(page_size=50, page_token="start-token")
        assert results == {"clients": "[]", "next-page-token": "more-pages-token"}
        assert "is-last-page" not in results

    @pytest.mark.parametrize(
        "params",
        [
            {"page-size": 0},
            {"page-size": -1},
            {"page-size": True},
            {"page-size": False},
            {"page-size": 10.0},
            {"page-size": 1.5},
            {"page-size": "10"},
            {"page-size": None},
            {"page-token": None},
            {"page-token": 123},
            {"page-token": True},
            {"page-token": ["token"]},
        ],
    )
    def test_invalid_pagination_inputs_fail_before_io(
        self,
        listing: OAuthClientRetriever,
        cli: MagicMock,
        params: dict[str, object],
    ) -> None:
        with pytest.raises(OAuthClientListingError):
            listing.run(params)

        cli.list_oauth_clients.assert_not_called()

    @pytest.mark.parametrize(
        "export_value",
        ["", "true", True, False, "yaml", "csv", None, 123],
    )
    def test_unsupported_export_format_identifies_json(
        self,
        listing: OAuthClientRetriever,
        cli: MagicMock,
        export_value: object,
    ) -> None:
        with pytest.raises(OAuthClientListingError, match="json"):
            listing.run({"export": export_value})

        cli.list_oauth_clients.assert_not_called()

    def test_export_with_non_empty_page_token_fails_before_io(
        self, listing: OAuthClientRetriever, cli: MagicMock, tmp_path: Path
    ) -> None:
        with pytest.raises(OAuthClientListingError, match="first page"):
            listing.run({"export": "json", "page-token": "continuation-token"})

        cli.list_oauth_clients.assert_not_called()
        assert list(tmp_path.iterdir()) == []


class TestInlineResultBudget:
    def test_format_action_result_args_matches_installed_ops_transport(self) -> None:
        results = {"clients": '[{"client-id": "c1"}]', "next-page-token": "tok-1"}
        backend = _ModelBackend("hydra/0")

        with patch("ops.hookcmds._action.run") as mock_run:
            backend.action_set(results)

        assert mock_run.call_args.args == ("action-set", *format_action_result_args(results))

    def test_exact_inline_byte_budget_boundary(
        self, listing: OAuthClientRetriever, cli: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        base_client = OAuthClient(client_id="c1", name="", client_secret="s3cr3t-not-logged")
        empty_name_page = OAuthClientPage(items=[base_client], next_page_token=None)
        base_results = {"clients": json.dumps([serialize_oauth_client(base_client)])}
        base_size = encoded_action_results_size(base_results)
        filler_len = OAUTH_CLIENT_INLINE_RESULT_BUDGET_BYTES - base_size
        assert filler_len > 0

        exact_client = empty_name_page.items[0].model_copy(update={"name": "a" * filler_len})
        cli.list_oauth_clients.return_value = OAuthClientPage(
            items=[exact_client], next_page_token=None
        )
        exact_results = listing.run({})
        assert (
            encoded_action_results_size(exact_results) == OAUTH_CLIENT_INLINE_RESULT_BUDGET_BYTES
        )

        over_client = empty_name_page.items[0].model_copy(update={"name": "a" * (filler_len + 1)})
        cli.list_oauth_clients.return_value = OAuthClientPage(
            items=[over_client], next_page_token=None
        )
        with (
            caplog.at_level(logging.DEBUG),
            pytest.raises(
                OAuthClientListingError, match="smaller page-size or export=json"
            ) as err,
        ):
            listing.run({})

        assert "s3cr3t-not-logged" not in str(err.value)
        assert "s3cr3t-not-logged" not in caplog.text
        assert "aaaa" not in str(err.value)
        assert "aaaa" not in caplog.text

    def test_json_escaping_and_unicode_counted_in_inline_budget(
        self, listing: OAuthClientRetriever, cli: MagicMock
    ) -> None:
        base_client = OAuthClient(client_id="c1", name="")
        base_size = encoded_action_results_size({
            "clients": json.dumps([serialize_oauth_client(base_client)])
        })
        remaining = OAUTH_CLIENT_INLINE_RESULT_BUDGET_BYTES - base_size
        # Each quote '"' is escaped as '\"' (2 bytes in json.dumps output).
        quote_count = (remaining // 2) + 1
        escaped_client = OAuthClient(client_id="c1", name='"' * quote_count)
        cli.list_oauth_clients.return_value = OAuthClientPage(
            items=[escaped_client], next_page_token=None
        )

        with pytest.raises(OAuthClientListingError, match="smaller page-size or export=json"):
            listing.run({})

        # Non-ASCII BMP char 'é' is escaped by json.dumps as '\u00e9' (6 bytes).
        unicode_count = (remaining // 6) + 1
        unicode_client = OAuthClient(client_id="c1", name="é" * unicode_count)
        cli.list_oauth_clients.return_value = OAuthClientPage(
            items=[unicode_client], next_page_token=None
        )

        with pytest.raises(OAuthClientListingError, match="smaller page-size or export=json"):
            listing.run({})

    def test_oversized_continuation_token_counted_in_inline_budget(
        self, listing: OAuthClientRetriever, cli: MagicMock
    ) -> None:
        # Multi-byte UTF-8 characters in next-page-token ('é' is 2 bytes in UTF-8)
        token = "é" * (OAUTH_CLIENT_INLINE_RESULT_BUDGET_BYTES // 2)
        cli.list_oauth_clients.return_value = OAuthClientPage(items=[], next_page_token=token)

        with pytest.raises(
            OAuthClientListingError, match="smaller page-size or export=json"
        ) as err:
            listing.run({})

        assert token not in str(err.value)


class TestFileExport:
    def test_serialization_timeout_preserves_previous_export(
        self, cli: MagicMock, tmp_path: Path
    ) -> None:
        now = 0.0

        def clock() -> float:
            return now

        def slow_serialize(client: OAuthClient) -> dict[str, object]:
            nonlocal now
            now = 301.0
            return serialize_oauth_client(client)

        export_dir = tmp_path / OAUTH_CLIENT_EXPORT_DIR
        export_dir.mkdir()
        final_path = export_dir / OAUTH_CLIENT_EXPORT_FILE_NAME
        final_path.write_text("[]", encoding="utf-8")
        cli.list_oauth_clients.return_value = OAuthClientPage(items=[OAuthClient(client_id="new")])
        service = OAuthClientRetriever(cli, tmp_path, "hydra/0", clock=clock)

        with patch("oauth_client_listing.serialize_oauth_client", side_effect=slow_serialize):
            with pytest.raises(OAuthClientListingError, match="timed out"):
                service.run({"export": "json"})

        assert final_path.read_text(encoding="utf-8") == "[]"
        assert list(export_dir.iterdir()) == [final_path]

    @pytest.mark.parametrize(
        "total_clients, page_size", [(0, 100), (100, 100), (101, 100), (6, 2)]
    )
    def test_export_writes_complete_inventory_across_pages(
        self,
        cli: MagicMock,
        tmp_path: Path,
        total_clients: int,
        page_size: int,
    ) -> None:
        all_clients = [
            OAuthClient(
                client_id=f"client-{idx}",
                client_secret=f"secret-{idx}",
                name=f"App {idx}",
            )
            for idx in range(total_clients)
        ]
        pages: list[OAuthClientPage] = []
        if total_clients == 0:
            pages.append(OAuthClientPage(items=[], next_page_token=None))
        else:
            for start in range(0, total_clients, page_size):
                batch = all_clients[start : start + page_size]
                next_start = start + page_size
                token = f"token-{next_start}" if next_start < total_clients else None
                pages.append(OAuthClientPage(items=batch, next_page_token=token))

        cli.list_oauth_clients.side_effect = pages
        service = OAuthClientRetriever(cli, tmp_path, "hydra/0")

        results = service.run({"export": "json", "page-size": page_size})

        expected_path = (
            tmp_path.resolve() / OAUTH_CLIENT_EXPORT_DIR / OAUTH_CLIENT_EXPORT_FILE_NAME
        )
        assert results == {
            "export-path": str(expected_path),
            "export-unit": "hydra/0",
            "export-container": OAUTH_CLIENT_EXPORT_CONTAINER,
            "client-count": total_clients,
        }
        assert "clients" not in results
        assert "next-page-token" not in results
        assert "is-last-page" not in results

        raw_content = expected_path.read_text(encoding="utf-8")
        assert "secret-" not in raw_content
        exported = json.loads(raw_content)
        assert len(exported) == total_clients
        assert [item["client-id"] for item in exported] == [
            f"client-{idx}" for idx in range(total_clients)
        ]

    def test_export_follows_short_and_empty_pages_with_continuation(
        self, listing: OAuthClientRetriever, cli: MagicMock, tmp_path: Path
    ) -> None:
        cli.list_oauth_clients.side_effect = [
            OAuthClientPage(items=[], next_page_token="tok-1"),
            OAuthClientPage(items=[OAuthClient(client_id="c1")], next_page_token="tok-2"),
            OAuthClientPage(items=[], next_page_token="tok-3"),
            OAuthClientPage(
                items=[OAuthClient(client_id="c2"), OAuthClient(client_id="c3")],
                next_page_token=None,
            ),
        ]

        results = listing.run({"export": "json", "page-size": 10})

        assert results["client-count"] == 3
        export_path = Path(str(results["export-path"]))
        exported = json.loads(export_path.read_text(encoding="utf-8"))
        assert [c["client-id"] for c in exported] == ["c1", "c2", "c3"]

    def test_export_permissions_and_atomic_latest_only_replacement(
        self, listing: OAuthClientRetriever, cli: MagicMock, tmp_path: Path
    ) -> None:
        export_dir = tmp_path / OAUTH_CLIENT_EXPORT_DIR
        export_dir.mkdir(mode=0o755)

        cli.list_oauth_clients.return_value = OAuthClientPage(
            items=[OAuthClient(client_id="old-client")], next_page_token=None
        )
        first_results = listing.run({"export": "json"})
        export_path = Path(str(first_results["export-path"]))

        assert stat.S_IMODE(export_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(export_path.stat().st_mode) == 0o600
        assert json.loads(export_path.read_text(encoding="utf-8"))[0]["client-id"] == "old-client"

        cli.list_oauth_clients.return_value = OAuthClientPage(
            items=[OAuthClient(client_id="new-client-1"), OAuthClient(client_id="new-client-2")],
            next_page_token=None,
        )
        second_results = listing.run({"export": "json"})

        assert second_results["client-count"] == 2
        assert [p.name for p in export_dir.iterdir()] == [OAUTH_CLIENT_EXPORT_FILE_NAME]
        assert stat.S_IMODE(export_path.stat().st_mode) == 0o600
        exported = json.loads(export_path.read_text(encoding="utf-8"))
        assert [c["client-id"] for c in exported] == ["new-client-1", "new-client-2"]

    def test_export_cleans_abandoned_temp_files_and_preserves_previous_export_on_failure(
        self, listing: OAuthClientRetriever, cli: MagicMock, tmp_path: Path
    ) -> None:
        export_dir = tmp_path / OAUTH_CLIENT_EXPORT_DIR
        export_dir.mkdir(mode=0o700)
        final_path = export_dir / OAUTH_CLIENT_EXPORT_FILE_NAME
        final_path.write_text('[{"client-id": "preserved"}]', encoding="utf-8")
        abandoned_1 = export_dir / ".oauth-clients-abandoned.tmp"
        abandoned_2 = export_dir / "stale-export.tmp"
        abandoned_1.write_text("partial-1", encoding="utf-8")
        abandoned_2.write_text("partial-2", encoding="utf-8")

        cli.list_oauth_clients.side_effect = [
            OAuthClientPage(items=[OAuthClient(client_id="c1")], next_page_token="tok-2"),
            OAuthClientListingError("Failed to list OAuth clients: hydra exited with code 1"),
        ]

        with pytest.raises(OAuthClientListingError, match="Failed to list OAuth clients"):
            listing.run({"export": "json"})

        assert not abandoned_1.exists()
        assert not abandoned_2.exists()
        assert [p.name for p in export_dir.iterdir()] == [OAUTH_CLIENT_EXPORT_FILE_NAME]
        assert final_path.read_text(encoding="utf-8") == '[{"client-id": "preserved"}]'

    def test_export_detects_multi_step_token_cycle_and_preserves_previous_export(
        self,
        listing: OAuthClientRetriever,
        cli: MagicMock,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        export_dir = tmp_path / OAUTH_CLIENT_EXPORT_DIR
        export_dir.mkdir(mode=0o700)
        final_path = export_dir / OAUTH_CLIENT_EXPORT_FILE_NAME
        final_path.write_text('[{"client-id": "previous"}]', encoding="utf-8")

        cli.list_oauth_clients.side_effect = [
            OAuthClientPage(
                items=[OAuthClient(client_id="c1", client_secret="sec-1")],
                next_page_token="tok-alpha",
            ),
            OAuthClientPage(
                items=[OAuthClient(client_id="c2", client_secret="sec-2")],
                next_page_token="tok-beta",
            ),
            OAuthClientPage(
                items=[OAuthClient(client_id="c3", client_secret="sec-3")],
                next_page_token="tok-alpha",
            ),
        ]

        with (
            caplog.at_level(logging.DEBUG),
            pytest.raises(OAuthClientListingError, match="cycle") as err,
        ):
            listing.run({"export": "json"})

        assert "tok-alpha" not in str(err.value)
        assert "tok-alpha" not in caplog.text
        assert "sec-1" not in caplog.text
        assert [p.name for p in export_dir.iterdir()] == [OAUTH_CLIENT_EXPORT_FILE_NAME]
        assert final_path.read_text(encoding="utf-8") == '[{"client-id": "previous"}]'

    def test_export_enforces_five_minute_deadline_and_caps_fetch_timeout(
        self, cli: MagicMock, tmp_path: Path
    ) -> None:
        assert OAUTH_CLIENT_EXPORT_TIMEOUT_SECONDS == 300.0
        now = 1000.0

        def clock() -> float:
            return now

        def fetch_page(page_size: int, page_token: str, timeout: float = 20.0) -> OAuthClientPage:
            nonlocal now
            if page_token == "":
                assert timeout == 20.0
                now = 1295.0  # 5s remaining before 1300.0 deadline
                return OAuthClientPage(
                    items=[OAuthClient(client_id="c1")], next_page_token="tok-2"
                )
            assert timeout == pytest.approx(5.0)
            now = 1300.0  # Deadline reached before page 3
            return OAuthClientPage(items=[OAuthClient(client_id="c2")], next_page_token="tok-3")

        cli.list_oauth_clients.side_effect = fetch_page
        export_dir = tmp_path / OAUTH_CLIENT_EXPORT_DIR
        export_dir.mkdir(mode=0o700)
        final_path = export_dir / OAUTH_CLIENT_EXPORT_FILE_NAME
        final_path.write_text('[{"client-id": "kept"}]', encoding="utf-8")

        service = OAuthClientRetriever(cli, tmp_path, "hydra/0", clock=clock)

        with pytest.raises(OAuthClientListingError, match="timed out"):
            service.run({"export": "json"})

        assert [p.name for p in export_dir.iterdir()] == [OAUTH_CLIENT_EXPORT_FILE_NAME]
        assert final_path.read_text(encoding="utf-8") == '[{"client-id": "kept"}]'

    def test_export_aborts_when_single_page_exceeds_deadline(
        self, cli: MagicMock, tmp_path: Path
    ) -> None:
        now = 1000.0

        def clock() -> float:
            return now

        def slow_page(page_size: int, page_token: str, timeout: float = 20.0) -> OAuthClientPage:
            nonlocal now
            now = 1301.0
            return OAuthClientPage(items=[OAuthClient(client_id="c1")], next_page_token=None)

        cli.list_oauth_clients.side_effect = slow_page
        service = OAuthClientRetriever(cli, tmp_path, "hydra/0", clock=clock)

        with pytest.raises(OAuthClientListingError, match="timed out"):
            service.run({"export": "json"})

    def test_export_enforces_exact_byte_limit_and_cleans_up_on_overflow(
        self,
        cli: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        assert OAUTH_CLIENT_EXPORT_MAX_BYTES == 100 * 1024 * 1024
        base_client = OAuthClient(client_id="c1", name="", client_secret="secret-not-leaked")
        empty_serialized = json.dumps([serialize_oauth_client(base_client)]).encode("utf-8")
        custom_limit = len(empty_serialized) + 32
        monkeypatch.setattr("oauth_client_listing.OAUTH_CLIENT_EXPORT_MAX_BYTES", custom_limit)

        exact_client = base_client.model_copy(update={"name": "x" * 32})
        cli.list_oauth_clients.return_value = OAuthClientPage(
            items=[exact_client], next_page_token=None
        )
        service = OAuthClientRetriever(cli, tmp_path, "hydra/0")

        results = service.run({"export": "json"})
        final_path = Path(str(results["export-path"]))
        assert final_path.stat().st_size == custom_limit

        over_client = base_client.model_copy(update={"name": "x" * 33})
        cli.list_oauth_clients.return_value = OAuthClientPage(
            items=[over_client], next_page_token=None
        )
        with pytest.raises(OAuthClientListingError, match="100 MiB") as err:
            service.run({"export": "json"})

        assert "secret-not-leaked" not in str(err.value)
        assert final_path.stat().st_size == custom_limit
        assert [p.name for p in final_path.parent.iterdir()] == [OAUTH_CLIENT_EXPORT_FILE_NAME]

    @pytest.mark.parametrize("failure_stage", ["mkdir", "write", "close", "replace"])
    def test_export_file_write_close_and_replace_failures_preserve_previous_export(
        self,
        listing: OAuthClientRetriever,
        cli: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        failure_stage: str,
    ) -> None:
        export_dir = tmp_path / OAUTH_CLIENT_EXPORT_DIR
        export_dir.mkdir(mode=0o700)
        final_path = export_dir / OAUTH_CLIENT_EXPORT_FILE_NAME
        final_path.write_text('[{"client-id": "existing"}]', encoding="utf-8")
        subdir = export_dir / "nested-dir"
        subdir.mkdir()

        cli.list_oauth_clients.return_value = OAuthClientPage(
            items=[OAuthClient(client_id="new-client", client_secret="secret-in-flight")],
            next_page_token=None,
        )

        real_fdopen = os.fdopen
        if failure_stage == "mkdir":
            monkeypatch.setattr(
                Path,
                "mkdir",
                MagicMock(side_effect=OSError("permission denied secret-in-flight")),
            )
        elif failure_stage == "write":

            def failing_fdopen(fd: int, mode: str = "r") -> object:
                f = real_fdopen(fd, mode)
                wrapper = MagicMock(wraps=f)
                wrapper.write.side_effect = OSError("disk full new-client secret-in-flight")
                wrapper.close.side_effect = f.close
                return wrapper

            monkeypatch.setattr("oauth_client_listing.os.fdopen", failing_fdopen)
        elif failure_stage == "close":

            def failing_close_fdopen(fd: int, mode: str = "r") -> object:
                f = real_fdopen(fd, mode)
                wrapper = MagicMock(wraps=f)

                def close_and_fail() -> None:
                    f.close()
                    raise OSError("flush failed on close secret-in-flight")

                wrapper.close.side_effect = close_and_fail
                return wrapper

            monkeypatch.setattr("oauth_client_listing.os.fdopen", failing_close_fdopen)
        else:
            monkeypatch.setattr(
                "oauth_client_listing.os.replace",
                MagicMock(side_effect=OSError("replace failed secret-in-flight")),
            )

        with (
            caplog.at_level(logging.DEBUG),
            pytest.raises(OAuthClientListingError) as err,
        ):
            listing.run({"export": "json"})

        assert "secret-in-flight" not in str(err.value)
        assert "secret-in-flight" not in caplog.text
        assert "new-client" not in str(err.value)
        assert sorted(p.name for p in export_dir.iterdir()) == [
            "nested-dir",
            OAUTH_CLIENT_EXPORT_FILE_NAME,
        ]
        assert final_path.read_text(encoding="utf-8") == '[{"client-id": "existing"}]'
