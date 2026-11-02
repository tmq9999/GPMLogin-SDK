"""Resource classes for the GPM Login local API (sync and async variants side by side)."""

from __future__ import annotations

from .browsers import AsyncBrowsersResource, BrowsersResource
from .profiles import AsyncProfilesResource, ProfilesResource

__all__ = [
    "AsyncBrowsersResource",
    "AsyncProfilesResource",
    "BrowsersResource",
    "ProfilesResource",
]
