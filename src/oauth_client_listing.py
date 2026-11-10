# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import contextlib
import json
import logging
import os
import tempfile
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import BinaryIO, cast

from ops.model import _format_action_result_dict

from cli import CommandLine, OAuthClient, OAuthClientPage
from constants import (
    DEFAULT_OAUTH_CLIENT_PAGE_SIZE,
    OAUTH_CLIENT_EXPORT_CONTAINER,
    OAUTH_CLIENT_EXPORT_DIR,
    OAUTH_CLIENT_EXPORT_FILE_NAME,
    OAUTH_CLIENT_EXPORT_FORMAT_JSON,
    OAUTH_CLIENT_EXPORT_MAX_BYTES,
    OAUTH_CLIENT_EXPORT_TIMEOUT_SECONDS,
    OAUTH_CLIENT_INLINE_RESULT_BUDGET_BYTES,
)
from exceptions import OAuthClientListingError

logger = logging.getLogger(__name__)

DEFAULT_CLI_PAGE_TIMEOUT_SECONDS = 20.0


def serialize_oauth_client(client: OAuthClient) -> dict[str, object]:
    """Serialize an OAuthClient for action output or export, excluding its secret."""
    return client.model_dump(
        by_alias=True,
        exclude_none=True,
        exclude={"client_secret"},
        mode="json",
    )


def format_action_result_args(results: Mapping[str, object]) -> list[str]:
    """Build the flattened `key=value` arguments that Ops passes to `action-set`."""
    flat_results = _format_action_result_dict(dict(results))
    return [f"{key}={value}" for key, value in flat_results.items()]


def encoded_action_results_size(results: Mapping[str, object]) -> int:
    """Return the byte size of UTF-8 encoded `key=value` arguments including null terminators."""
    return sum(len(arg.encode("utf-8")) + 1 for arg in format_action_result_args(results))


class OAuthClientRetriever:
    """Domain service for paginated OAuth client listing and export."""

    def __init__(
        self,
        cli: CommandLine,
        charm_dir: Path,
        unit_name: str,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cli = cli
        self._charm_dir = Path(charm_dir)
        self._unit_name = unit_name
        self._clock = clock

    def run(self, params: Mapping[str, object]) -> dict[str, str | int]:
        """Validate action parameters and perform inline listing or JSON export."""
        page_size, page_token, export_format = self._validate_params(params)
        if export_format == OAUTH_CLIENT_EXPORT_FORMAT_JSON:
            return self._export_clients(page_size)
        return self._list_clients_inline(page_size, page_token)

    def _validate_params(self, params: Mapping[str, object]) -> tuple[int, str, str | None]:
        page_size = params.get("page-size", DEFAULT_OAUTH_CLIENT_PAGE_SIZE)
        if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size < 1:
            raise OAuthClientListingError("Invalid page-size: must be a positive integer")

        page_token = params.get("page-token", "")
        if not isinstance(page_token, str):
            raise OAuthClientListingError("Invalid page-token: must be a string")

        export_format: str | None = None
        if "export" in params:
            raw_export = params["export"]
            if not isinstance(raw_export, str) or raw_export != OAUTH_CLIENT_EXPORT_FORMAT_JSON:
                raise OAuthClientListingError(
                    f"Unsupported export format: only '{OAUTH_CLIENT_EXPORT_FORMAT_JSON}' is supported"
                )
            if page_token:
                raise OAuthClientListingError(
                    "Cannot combine export=json with page-token: export always starts from the first page"
                )
            export_format = raw_export

        return page_size, page_token, export_format

    def _list_clients_inline(self, page_size: int, page_token: str) -> dict[str, str | int]:
        page = self._cli.list_oauth_clients(page_size=page_size, page_token=page_token)
        clients = [serialize_oauth_client(client) for client in page.items]
        results: dict[str, str | int] = {"clients": json.dumps(clients)}
        if page.next_page_token:
            results["next-page-token"] = page.next_page_token
        self._ensure_within_result_budget(results)
        return results

    def _export_clients(self, page_size: int) -> dict[str, str | int]:
        deadline = self._clock() + OAUTH_CLIENT_EXPORT_TIMEOUT_SECONDS
        export_dir = self._charm_dir.resolve() / OAUTH_CLIENT_EXPORT_DIR
        final_path = export_dir / OAUTH_CLIENT_EXPORT_FILE_NAME
        temp_path: Path | None = None
        temp_file: BinaryIO | None = None
        try:
            export_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            export_dir.chmod(0o700)
            self._remove_abandoned_temp_files(export_dir)
            fd, temp_name = tempfile.mkstemp(
                prefix=".oauth-clients-",
                suffix=".tmp",
                dir=export_dir,
            )
            temp_path = Path(temp_name)
            temp_file = cast(BinaryIO, os.fdopen(fd, "wb"))
            os.chmod(temp_path, 0o600)

            client_count = self._stream_export_pages(temp_file, page_size, deadline)
            temp_file.flush()
            temp_file.close()
            temp_file = None

            results: dict[str, str | int] = {
                "export-path": str(final_path),
                "export-unit": self._unit_name,
                "export-container": OAUTH_CLIENT_EXPORT_CONTAINER,
                "client-count": client_count,
            }
            self._ensure_within_result_budget(results)
            if self._clock() >= deadline:
                raise OAuthClientListingError("OAuth client export timed out")
            os.replace(temp_path, final_path)
            return results
        except OAuthClientListingError:
            self._cleanup_temp_export(temp_file, temp_path)
            raise
        except OSError as err:
            self._cleanup_temp_export(temp_file, temp_path)
            logger.error("Failed to write OAuth client export file")
            raise OAuthClientListingError("Failed to write OAuth client export file") from err

    @staticmethod
    def _remove_abandoned_temp_files(export_dir: Path) -> None:
        for entry in export_dir.iterdir():
            if entry.name != OAUTH_CLIENT_EXPORT_FILE_NAME and not entry.is_dir():
                entry.unlink(missing_ok=True)

    def _stream_export_pages(self, temp_file: BinaryIO, page_size: int, deadline: float) -> int:
        bytes_written = 0
        client_count = 0
        page_token = ""
        seen_tokens: set[str] = set()

        bytes_written = self._write_bounded(temp_file, b"[", bytes_written)
        while True:
            page = self._fetch_export_page(page_size, page_token, deadline)
            for client in page.items:
                serialized = json.dumps(serialize_oauth_client(client)).encode("utf-8")
                if self._clock() >= deadline:
                    raise OAuthClientListingError("OAuth client export timed out")
                prefix = b", " if client_count > 0 else b""
                bytes_written = self._write_bounded(temp_file, prefix + serialized, bytes_written)
                client_count += 1

            next_token = page.next_page_token
            if not next_token:
                break
            if next_token in seen_tokens:
                raise OAuthClientListingError(
                    "OAuth client export aborted: pagination token cycle detected"
                )
            seen_tokens.add(next_token)
            page_token = next_token

        self._write_bounded(temp_file, b"]", bytes_written)
        return client_count

    def _fetch_export_page(
        self, page_size: int, page_token: str, deadline: float
    ) -> OAuthClientPage:
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise OAuthClientListingError("OAuth client export timed out")
        timeout = min(DEFAULT_CLI_PAGE_TIMEOUT_SECONDS, remaining)
        page = self._cli.list_oauth_clients(
            page_size=page_size, page_token=page_token, timeout=timeout
        )
        if self._clock() > deadline:
            raise OAuthClientListingError("OAuth client export timed out")
        return page

    @staticmethod
    def _write_bounded(temp_file: BinaryIO, chunk: bytes, bytes_written: int) -> int:
        new_total = bytes_written + len(chunk)
        if new_total > OAUTH_CLIENT_EXPORT_MAX_BYTES:
            raise OAuthClientListingError("OAuth client export exceeds the 100 MiB size limit")
        temp_file.write(chunk)
        return new_total

    @staticmethod
    def _cleanup_temp_export(temp_file: BinaryIO | None, temp_path: Path | None) -> None:
        if temp_file is not None:
            with contextlib.suppress(OSError):
                temp_file.close()
        if temp_path is not None:
            with contextlib.suppress(OSError):
                temp_path.unlink(missing_ok=True)

    @staticmethod
    def _ensure_within_result_budget(results: Mapping[str, str | int]) -> None:
        if encoded_action_results_size(results) > OAUTH_CLIENT_INLINE_RESULT_BUDGET_BYTES:
            raise OAuthClientListingError(
                "OAuth client results exceed the inline size limit. "
                "Try a smaller page-size or export=json"
            )
