"""Drive a GPM Chrome profile with Playwright (asyncio API).

Requires: pip install ".[playwright]", GPM Login running, and GPM_PROFILE_ID naming a profile
that is a dedicated Chrome (Chromium-based) profile. Do not point this at a profile you are
using by hand: the session owns it and stops it at the end. Firefox profiles are not supported.

Nesting matters: Playwright is outermost, the profile session is next, and the CDP attachment
is innermost, so the attachment detaches before the profile is stopped.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from typing import Any

from gpmlogin_sdk import AsyncGPMClient, BrowserType
from gpmlogin_sdk.integrations.playwright import connect_async


async def main(
    client: AsyncGPMClient | None = None,
    profile_id: str | None = None,
    playwright: Any = None,
) -> list[str]:
    profile_id = profile_id or os.environ.get("GPM_PROFILE_ID")
    if not profile_id:
        raise SystemExit("Set GPM_PROFILE_ID to a dedicated Chrome profile.")
    lines: list[str] = []
    async with AsyncExitStack() as stack:
        if playwright is None:
            from playwright.async_api import async_playwright

            playwright = await stack.enter_async_context(async_playwright())
        gpm = client or await stack.enter_async_context(AsyncGPMClient())
        async with (
            gpm.profile_session(profile_id, exclusive=True) as session,
            connect_async(
                session.launch, playwright, browser_kind=BrowserType.CHROME
            ) as attachment,
        ):
            page = await attachment.get_or_create_page()
            await page.goto("https://example.com")
            lines.append(f"title: {await page.title()}")
    for line in lines:
        print(line)
    return lines


if __name__ == "__main__":
    asyncio.run(main())
