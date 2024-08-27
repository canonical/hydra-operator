# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.


class CharmError(Exception):
    """Base class for custom charm errors."""


class PebbleServiceError(CharmError):
    """Error for pebble related operations."""


class MigrationError(CharmError):
    """Error for migration plan."""
