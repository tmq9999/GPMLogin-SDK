from __future__ import annotations

import math
from pathlib import Path

import pytest

from gpmlogin_sdk.config import GPMConfig, resolve_config
from gpmlogin_sdk.errors import GPMConfigurationError

ENV_NAMES = ("GPM_API_HOST", "GPM_API_PORT", "GPM_API_TIMEOUT_SECONDS", "GPM_HTTP_PORT_FILE")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_defaults() -> None:
    config = resolve_config()
    assert config.base_url == "http://127.0.0.1:9495/api/v1"
    assert config.host == "127.0.0.1"
    assert config.port == 9495
    assert config.timeout == 30.0


def test_port_precedence_argument_over_env_over_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GPM_API_PORT", "9555")
    assert resolve_config(port=9666).port == 9666
    assert resolve_config().port == 9555


def test_localhost_is_allowed_and_normalised_for_lock_key() -> None:
    config = resolve_config(host="localhost", port=9001)
    assert config.base_url == "http://localhost:9001/api/v1"
    assert config.api_key == ("127.0.0.1", 9001)
    assert resolve_config(host="127.0.0.1", port=9001).api_key == config.api_key


def test_host_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GPM_API_HOST", "localhost")
    assert resolve_config().host == "localhost"
    assert resolve_config(host="127.0.0.1").host == "127.0.0.1"


@pytest.mark.parametrize(
    "host",
    [
        "example.com",
        "http://127.0.0.1",
        "127.0.0.1/path",
        "user@127.0.0.1",
        "127.0.0.1:9495",
        "::1",
        "[::1]",
        "0.0.0.0",
        "",
        " localhost",
        "localhost ",
    ],
)
def test_rejects_unsupported_hosts(host: str) -> None:
    with pytest.raises(GPMConfigurationError):
        resolve_config(host=host)


@pytest.mark.parametrize("port", [True, False, 0, -1, 65536, 1.5, "9495"])
def test_rejects_invalid_explicit_ports(port: object) -> None:
    with pytest.raises(GPMConfigurationError):
        resolve_config(port=port)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["abc", "", " ", "0", "65536", "-5", "95.5", "1e3", "٣٣"])
def test_rejects_invalid_env_port(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("GPM_API_PORT", value)
    with pytest.raises(GPMConfigurationError):
        resolve_config()


def test_config_file_and_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    explicit_file = tmp_path / "explicit.port"
    explicit_file.write_text("9777\n", encoding="utf-8")
    env_file = tmp_path / "env.port"
    env_file.write_text("9888\n", encoding="utf-8")

    monkeypatch.setenv("GPM_HTTP_PORT_FILE", str(env_file))
    assert resolve_config().port == 9888
    assert resolve_config(port_file=explicit_file).port == 9777
    assert resolve_config(port_file=str(explicit_file)).port == 9777

    monkeypatch.setenv("GPM_API_PORT", "9555")
    assert resolve_config().port == 9555, "env port outranks the port file"
    assert resolve_config(port=9666, port_file=explicit_file).port == 9666


def test_lower_priority_sources_are_not_read_when_a_higher_one_is_chosen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GPM_API_PORT", "not-a-number")
    monkeypatch.setenv("GPM_HTTP_PORT_FILE", str(tmp_path / "missing.port"))
    assert resolve_config(port=9666).port == 9666

    monkeypatch.setenv("GPM_API_PORT", "9555")
    assert resolve_config().port == 9555


@pytest.mark.parametrize("content", ["", "\n", "abc", '{"port": 9495}', "9495 9496", "0", "70000"])
def test_chosen_port_file_with_bad_content_raises(tmp_path: Path, content: str) -> None:
    port_file = tmp_path / "http.port"
    port_file.write_text(content, encoding="utf-8")
    with pytest.raises(GPMConfigurationError):
        resolve_config(port_file=port_file)


def test_chosen_port_file_missing_raises_without_fallback(tmp_path: Path) -> None:
    with pytest.raises(GPMConfigurationError):
        resolve_config(port_file=tmp_path / "missing.port")


def test_unreadable_port_file_raises(tmp_path: Path) -> None:
    with pytest.raises(GPMConfigurationError):
        resolve_config(port_file=tmp_path)  # a directory cannot be read as a file


def test_empty_env_port_file_path_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GPM_HTTP_PORT_FILE", "")
    with pytest.raises(GPMConfigurationError):
        resolve_config()


def test_timeout_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GPM_API_TIMEOUT_SECONDS", "12.5")
    assert resolve_config().timeout == 12.5
    assert resolve_config(timeout=3).timeout == 3.0


@pytest.mark.parametrize("timeout", [0, -1, math.nan, math.inf, True, "5"])
def test_rejects_invalid_timeout_argument(timeout: object) -> None:
    with pytest.raises(GPMConfigurationError):
        resolve_config(timeout=timeout)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["abc", "", "0", "-2", "nan", "inf"])
def test_rejects_invalid_timeout_env(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("GPM_API_TIMEOUT_SECONDS", value)
    with pytest.raises(GPMConfigurationError):
        resolve_config()


def test_config_is_frozen_and_instances_are_independent() -> None:
    first = resolve_config(port=9001)
    second = resolve_config(port=9002)
    assert isinstance(first, GPMConfig)
    assert first.port == 9001 and second.port == 9002
    with pytest.raises(AttributeError):
        first.port = 1  # type: ignore[misc]


def test_error_text_does_not_echo_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GPM_API_PORT", "SECRET")
    with pytest.raises(GPMConfigurationError) as caught:
        resolve_config()
    assert "SECRET" not in str(caught.value)
    assert "SECRET" not in repr(caught.value)
