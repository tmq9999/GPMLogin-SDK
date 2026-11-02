"""Local API address resolution.

Port precedence: ``port`` argument > ``GPM_API_PORT`` > port file > 9495. The port file path is the
``port_file`` argument or ``GPM_HTTP_PORT_FILE``. Only the first selected source is read; if it is
invalid the function raises instead of falling back. No port scanning is ever performed.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

from .errors import GPMConfigurationError

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9495
DEFAULT_TIMEOUT_SECONDS = 30.0

ENV_HOST = "GPM_API_HOST"
ENV_PORT = "GPM_API_PORT"
ENV_TIMEOUT = "GPM_API_TIMEOUT_SECONDS"
ENV_PORT_FILE = "GPM_HTTP_PORT_FILE"

_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost"})


@dataclass(frozen=True)
class GPMConfig:
    """Resolved, immutable address and timeout for the local GPM API."""

    host: str
    port: int
    timeout: float

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/api/v1"

    @property
    def api_key(self) -> tuple[str, int]:
        """Identity of the API endpoint; ``localhost`` and ``127.0.0.1`` are the same endpoint."""
        return ("127.0.0.1", self.port)


def _validate_host(value: object) -> str:
    if not isinstance(value, str) or value.lower() not in _ALLOWED_HOSTS:
        raise GPMConfigurationError("Only the hosts 'localhost' and '127.0.0.1' are supported.")
    return value.lower()


def _validate_port(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise GPMConfigurationError("The port must be an integer between 1 and 65535.")
    return value


def _parse_port_text(text: str) -> int:
    stripped = text.strip()
    if not (stripped.isascii() and stripped.isdigit()):
        raise GPMConfigurationError("The port must be an integer between 1 and 65535.")
    return _validate_port(int(stripped))


def _read_port_file(path_value: object) -> str | None:
    if not isinstance(path_value, str | os.PathLike) or path_value == "":
        return None
    try:
        return Path(path_value).read_text(encoding="utf-8-sig")
    except (OSError, ValueError):
        return None


def _resolve_port(port: int | None, port_file: str | os.PathLike[str] | None) -> int:
    if port is not None:
        return _validate_port(port)

    env_port = os.environ.get(ENV_PORT)
    if env_port is not None:
        return _parse_port_text(env_port)

    path_value: object = port_file
    if path_value is None:
        path_value = os.environ.get(ENV_PORT_FILE)
    if path_value is None:
        return DEFAULT_PORT

    text = _read_port_file(path_value)
    if text is None:
        raise GPMConfigurationError("The configured port file could not be read.")
    return _parse_port_text(text)


def _validate_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise GPMConfigurationError("The timeout must be a finite number of seconds above zero.")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise GPMConfigurationError("The timeout must be a finite number of seconds above zero.")
    return number


def _resolve_timeout(timeout: float | None) -> float:
    if timeout is not None:
        return _validate_timeout(timeout)
    env_timeout = os.environ.get(ENV_TIMEOUT)
    if env_timeout is None:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        parsed = float(env_timeout)
    except ValueError:
        parsed = math.nan
    return _validate_timeout(parsed)


def resolve_config(
    *,
    host: str | None = None,
    port: int | None = None,
    port_file: str | os.PathLike[str] | None = None,
    timeout: float | None = None,
) -> GPMConfig:
    """Resolve the local API address. Never reads the network or scans ports."""
    if host is None:
        host = os.environ.get(ENV_HOST, DEFAULT_HOST)
    return GPMConfig(
        host=_validate_host(host),
        port=_resolve_port(port, port_file),
        timeout=_resolve_timeout(timeout),
    )
