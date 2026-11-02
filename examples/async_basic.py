"""List a few profiles, then run one profile in an exclusive session (asyncio client).

Needs GPM Login running locally. Set GPM_PROFILE_ID to also start and stop that profile.
The session stops the profile when the block ends and never deletes it.
"""

from __future__ import annotations

import asyncio
import os

from gpmlogin_sdk import AsyncGPMClient


async def main(client: AsyncGPMClient | None = None, profile_id: str | None = None) -> list[str]:
    profile_id = profile_id or os.environ.get("GPM_PROFILE_ID")
    owned = client is None
    gpm = client or AsyncGPMClient()
    lines: list[str] = []
    try:
        for profile in (await gpm.profiles.list(page_size=5)).data:
            lines.append(f"profile {profile.id}: {profile.name}")
        if profile_id:
            details = await gpm.profiles.get(profile_id)
            lines.append(f"selected {details.id}: {details.name}")
            async with gpm.profile_session(profile_id, exclusive=True) as session:
                lines.append(f"started {session.profile_id}")
            lines.append(f"stopped {profile_id}")
        else:
            lines.append("set GPM_PROFILE_ID to start and stop one profile")
    finally:
        if owned:
            await gpm.aclose()
    for line in lines:
        print(line)
    return lines


if __name__ == "__main__":
    asyncio.run(main())
