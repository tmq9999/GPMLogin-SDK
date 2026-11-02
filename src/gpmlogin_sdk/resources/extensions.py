"""Extensions resource (2 endpoints): list, and enable/disable. Nothing else is documented."""

from __future__ import annotations

import builtins
from collections.abc import Sequence

from .._async_transport import AsyncTransport
from .._operations import Operation, parse_none
from .._serialization import encode_id
from .._transport import Transport
from ..errors import GPMValidationError
from ..models import Extension, parse_extensions
from ._common import Call


def list_call() -> Call[builtins.list[Extension]]:
    return Call(Operation("extensions.list", "GET", "/extensions", False, parse_extensions))


def _scope(group_ids: object) -> str | None:
    """Comma-joined group IDs, or None for global scope. An empty list is rejected on purpose."""
    if group_ids is None:
        return None
    if isinstance(group_ids, str | bytes) or not isinstance(group_ids, Sequence) or not group_ids:
        raise GPMValidationError("Invalid value for 'group_ids'.", field="group_ids")
    for group_id in group_ids:
        if not isinstance(group_id, str) or not group_id.strip() or "," in group_id:
            raise GPMValidationError("Invalid value for 'group_ids'.", field="group_ids")
    return ",".join(group_ids)


def set_state_call(extension_id: str, active: object, group_ids: object) -> Call[None]:
    path = f"/extensions/update-state/{encode_id(extension_id)}"
    if not isinstance(active, bool):
        raise GPMValidationError("Invalid value for 'active'.", field="active")
    query: dict[str, object] = {"active": active}
    scope = _scope(group_ids)
    if scope is not None:
        query["applied_group_ids"] = scope
    return Call(Operation("extensions.set_state", "GET", path, True, parse_none), query)


class ExtensionsResource:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def list(self) -> builtins.list[Extension]:
        """Installed extensions as a plain array (not a paginated result)."""
        return self._transport.request(list_call().operation)

    def set_state(
        self, extension_id: str, *, active: bool, group_ids: Sequence[str] | None = None
    ) -> None:
        """Enable or disable an extension. ``group_ids=None`` means global scope, which changes
        the extension for every group; pass a non-empty list to limit it."""
        call = set_state_call(extension_id, active, group_ids)
        self._transport.request(call.operation, query=call.query)


class AsyncExtensionsResource:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def list(self) -> builtins.list[Extension]:
        """Installed extensions as a plain array (not a paginated result)."""
        return await self._transport.request(list_call().operation)

    async def set_state(
        self, extension_id: str, *, active: bool, group_ids: Sequence[str] | None = None
    ) -> None:
        """Enable or disable an extension. ``group_ids=None`` means global scope, which changes
        the extension for every group; pass a non-empty list to limit it."""
        call = set_state_call(extension_id, active, group_ids)
        await self._transport.request(call.operation, query=call.query)
