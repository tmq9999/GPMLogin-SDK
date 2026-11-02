from __future__ import annotations

import importlib.metadata
import importlib.resources

import gpmlogin_sdk
from gpmlogin_sdk.errors import GPMConfigurationError, GPMError


def test_version_matches_distribution_metadata() -> None:
    assert gpmlogin_sdk.__version__ == "0.1.0"
    assert importlib.metadata.version("gpmlogin-sdk") == gpmlogin_sdk.__version__


def test_error_hierarchy_and_exports() -> None:
    assert issubclass(GPMConfigurationError, GPMError)
    assert issubclass(GPMError, Exception)
    assert gpmlogin_sdk.GPMError is GPMError
    assert gpmlogin_sdk.GPMConfigurationError is GPMConfigurationError


def test_package_ships_py_typed_marker() -> None:
    assert importlib.resources.files("gpmlogin_sdk").joinpath("py.typed").is_file()
