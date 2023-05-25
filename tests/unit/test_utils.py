# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from utils import normalise_url


def test_normalise_url_with_subpatch() -> None:
    url = "http://ingress:80/path/subpath"
    expected_url = "https://ingress/path/subpath"

    res_url = normalise_url(url)

    assert res_url == expected_url


def test_normalise_url_without_subpatch() -> None:
    url = "http://ingress:80/"
    expected_url = "https://ingress/"

    res_url = normalise_url(url)

    assert res_url == expected_url


def test_normalise_url_without_trailing_slash() -> None:
    url = "http://ingress:80"
    expected_url = "https://ingress"

    res_url = normalise_url(url)

    assert res_url == expected_url
