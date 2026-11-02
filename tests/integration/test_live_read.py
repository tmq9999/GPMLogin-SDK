from __future__ import annotations

import pytest

from gpmlogin_sdk import GPMClient

pytestmark = pytest.mark.live


def test_profiles_list_is_readable(live_client: GPMClient) -> None:
    page = live_client.profiles.list(page_size=5)
    assert page.current_page == 1


def test_browser_versions_are_readable(live_client: GPMClient) -> None:
    live_client.browsers.versions()


def test_extensions_are_listable(live_client: GPMClient) -> None:
    assert isinstance(live_client.extensions.list(), list)
