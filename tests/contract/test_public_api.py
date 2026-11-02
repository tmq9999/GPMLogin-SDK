from __future__ import annotations

import re
from pathlib import Path

import pytest

import gpmlogin_sdk
from gpmlogin_sdk import AsyncGPMClient, GPMClient
from tests.contract.cases import DOCUMENTED_ENDPOINTS

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = Path(gpmlogin_sdk.__file__).parent

EXPECTED_EXPORTS = {
    "GPMClient",
    "AsyncGPMClient",
    "ProfileSession",
    "GPMError",
    "GPMConfigurationError",
    "GPMValidationError",
    "GPMAmbiguousMatchError",
    "GPMOperationError",
    "GPMProtocolError",
    "GPMTransportError",
    "GPMTimeoutError",
    "GPMHTTPError",
    "GPMAPIError",
    "GPMProfileBusyError",
    "GPMCleanupError",
    "GPMIntegrationError",
    "Page",
    "ProfileSummary",
    "ProfileDetails",
    "ProfileCreated",
    "ProfileUpdated",
    "Group",
    "Proxy",
    "Extension",
    "BrowserInfo",
    "BrowserVersions",
    "StartResult",
    "CreateProfileRequest",
    "UpdateProfileRequest",
    "StartOptions",
    "BrowserType",
    "SortOrder",
    "build_start_options",
    "join_startup_urls",
}


def test_all_expected_names_are_exported_and_resolvable() -> None:
    exported = set(gpmlogin_sdk.__all__)
    assert exported >= EXPECTED_EXPORTS
    assert len(gpmlogin_sdk.__all__) == len(exported)
    for name in gpmlogin_sdk.__all__:
        assert hasattr(gpmlogin_sdk, name), name


def test_the_package_ships_a_type_marker() -> None:
    assert (PACKAGE / "py.typed").is_file()


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "docs/usage.md",
        "docs/api.md",
        "docs/compatibility.md",
        "examples/sync_basic.py",
        "examples/async_basic.py",
        "examples/sync_playwright.py",
        "examples/async_playwright.py",
        "tools/verify_dist.py",
    ],
)
def test_documented_files_exist(path: str) -> None:
    assert (ROOT / path).is_file()


def endpoint_rows() -> list[tuple[str, str, str]]:
    text = (ROOT / "docs" / "api.md").read_text(encoding="utf-8")
    pattern = r"\|\s*`(GET|POST) ([^`]+)`\s*\|\s*`([a-z_]+\.[a-z_]+)`"
    return re.findall(pattern, text)


def test_the_api_table_lists_exactly_the_20_documented_endpoints() -> None:
    rows = endpoint_rows()
    assert len(rows) == 20
    assert {(method, path) for method, path, _ in rows} == set(DOCUMENTED_ENDPOINTS)


def test_every_row_names_a_method_on_both_clients() -> None:
    sync_client = GPMClient()
    async_client = AsyncGPMClient()
    try:
        for _, _, dotted in endpoint_rows():
            resource, method = dotted.split(".")
            assert callable(getattr(getattr(sync_client, resource), method)), dotted
            assert callable(getattr(getattr(async_client, resource), method)), dotted
    finally:
        sync_client.close()


def test_readme_covers_install_extras_and_the_ownership_warning() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "python -m pip install ." in text
    assert '".[playwright]"' in text
    assert "exclusive=True" in text
    assert "not distributed" in text.lower()
    assert "not been tested against a real GPM" in text


def test_usage_covers_the_documented_pitfalls() -> None:
    text = (ROOT / "docs" / "usage.md").read_text(encoding="utf-8").lower()
    for phrase in (
        "gpm_api_port",
        "http_client",
        "ambiguous",
        "race",
        "cancel",
        "confirm=true",
        "omitted",
        "extension",
        "state_uncertain",
    ):
        assert phrase in text, phrase


def test_compatibility_separates_documented_mocked_and_live() -> None:
    text = (ROOT / "docs" / "compatibility.md").read_text(encoding="utf-8").lower()
    for phrase in ("documented", "mocked", "live", "unverified", "econnrefused", "asyncio"):
        assert phrase in text, phrase
