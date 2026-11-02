"""Drive a GPM Chrome profile with Playwright (blocking API).

Requires: pip install ".[playwright]", GPM Login running, and GPM_PROFILE_ID naming a profile
that is a dedicated Chrome (Chromium-based) profile. Do not point this at a profile you are
using by hand: the session owns it and stops it at the end. Firefox profiles are not supported.

Nesting matters: Playwright is outermost, the profile session is next, and the CDP attachment
is innermost, so the attachment detaches before the profile is stopped.
"""

from __future__ import annotations

import os
from contextlib import ExitStack
from typing import Any

from gpmlogin_sdk import BrowserType, GPMClient
from gpmlogin_sdk.integrations.playwright import connect


def main(
    client: GPMClient | None = None,
    profile_id: str | None = None,
    playwright: Any = None,
) -> list[str]:
    profile_id = profile_id or os.environ.get("GPM_PROFILE_ID")
    if not profile_id:
        raise SystemExit("Set GPM_PROFILE_ID to a dedicated Chrome profile.")
    lines: list[str] = []
    with ExitStack() as stack:
        if playwright is None:
            from playwright.sync_api import sync_playwright

            playwright = stack.enter_context(sync_playwright())
        gpm = client or stack.enter_context(GPMClient())
        with (
            gpm.profile_session(profile_id, exclusive=True) as session,
            connect(session.launch, playwright, browser_kind=BrowserType.CHROME) as attachment,
        ):
            page = attachment.get_or_create_page()
            page.goto("https://example.com")
            lines.append(f"title: {page.title()}")
    for line in lines:
        print(line)
    return lines


if __name__ == "__main__":
    main()
