# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.


class CharmError(Exception):
    """Base class for custom charm errors."""


class PebbleServiceError(CharmError):
    """Error for pebble related operations."""


class CommandExecError(CharmError):
    """Error for pebble exec related operations."""


class ClientDoesNotExistError(CharmError):
    """Error for when a client does not exist."""


class MigrationError(CharmError):
    """Error for migration plan."""


class InvalidHydraConfig(CharmError):
    """Error for invalid hydra config."""
