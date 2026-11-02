"""Mutating live tests. They only touch records they create, and never hard delete."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest

from gpmlogin_sdk import BrowserType, GPMClient, GPMTimeoutError
from gpmlogin_sdk.integrations.playwright import connect


@dataclass
class Fixture:
    profile_id: str
    name: str
    stop_confirmed: bool = True
    notes: list[str] = field(default_factory=list)


@pytest.fixture
def created_profile(live_client: GPMClient) -> Iterator[Fixture]:
    name = f"sdk-live-{uuid.uuid4().hex[:12]}"
    created = live_client.profiles.create({"name": name})
    fixture = Fixture(profile_id=created.id, name=name)
    yield fixture
    if fixture.stop_confirmed:
        live_client.profiles.soft_delete(fixture.profile_id)
    else:
        print(f"RECONCILE MANUALLY: profile {fixture.profile_id} may still be running")


@pytest.mark.live_mutations
def test_created_profile_can_be_read_and_renamed(
    live_client: GPMClient, created_profile: Fixture
) -> None:
    assert live_client.profiles.get(created_profile.profile_id).name == created_profile.name
    new_name = created_profile.name + "-renamed"
    live_client.profiles.update(created_profile.profile_id, {"name": new_name})
    assert live_client.profiles.get(created_profile.profile_id).name == new_name


@pytest.mark.live_mutations
@pytest.mark.live_start
def test_session_starts_attaches_and_stops(
    live_client: GPMClient, created_profile: Fixture
) -> None:
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    created_profile.stop_confirmed = False
    try:
        with sync_playwright() as pw:
            with live_client.profile_session(created_profile.profile_id, exclusive=True) as session:
                with connect(session.launch, pw, browser_kind=BrowserType.CHROME) as attachment:
                    attachment.get_or_create_page()
        created_profile.stop_confirmed = True
    except GPMTimeoutError:
        created_profile.notes.append("start timed out; state unknown")
        raise


@pytest.mark.live_shared_mutations
def test_group_and_proxy_records_created_here_can_be_managed(live_client: GPMClient) -> None:
    suffix = uuid.uuid4().hex[:12]
    group = live_client.groups.create(f"sdk-live-{suffix}")
    try:
        live_client.groups.update(group.id, name=f"sdk-live-{suffix}-b")
    finally:
        live_client.groups.delete(group.id, confirm=True)

    proxy = live_client.proxies.create("socks5://127.0.0.1:1")
    try:
        live_client.proxies.update(proxy.id, "socks5://127.0.0.1:2")
    finally:
        live_client.proxies.delete(proxy.id, confirm=True)
