# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest

from utils import is_newer_version


@pytest.mark.parametrize(
    "version, than, expected",
    [
        ("v26.2.0", "v25.4.0", True),
        ("v2.10.0", "v2.9.0", True),
        ("v1.0.1", "v1.0.0", True),
        ("v1.0.0", "v1.0.0", False),
        ("v25.4.0", "v26.2.0", False),
        ("", "v1.0.0", False),
        ("unknown", "v1.0.0", False),
        ("v1.0.0", "", False),
    ],
)
def test_is_newer_version(version: str, than: str, expected: bool) -> None:
    assert is_newer_version(version, than) is expected
