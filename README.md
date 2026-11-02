# gpmlogin-sdk

Typed Python client for the GPM Login local HTTP API. It covers all 20
documented endpoints with a blocking client (`GPMClient`) and an asyncio client
(`AsyncGPMClient`), plus optional helpers for exclusive profile sessions and Playwright.

Status: experimental, version 0.1.0. The SDK has been tested only against mocked HTTP and a
local Playwright error spike. It has not been tested against a real GPM Login instance. See
[docs/compatibility.md](docs/compatibility.md).

## Install

From a checkout (nothing is published to PyPI):

```powershell
python -m pip install .
python -m pip install ".[playwright]"   # optional, adds the Playwright adapter
```

Python 3.11 or newer. The core install needs only `httpx`.

## Blocking use

```python
from gpmlogin_sdk import GPMClient

with GPMClient() as client:  # 127.0.0.1:9495 unless configured
    for profile in client.profiles.iter_all():
        print(profile.id, profile.name)

    with client.profile_session("PROFILE_ID", exclusive=True) as session:
        print("started", session.profile_id)
    # the profile is stopped here, at most once, and never deleted
```

## Asyncio use

```python
import asyncio
from gpmlogin_sdk import AsyncGPMClient

async def main() -> None:
    async with AsyncGPMClient() as client:
        async for profile in client.profiles.iter_all():
            print(profile.id, profile.name)
        async with client.profile_session("PROFILE_ID", exclusive=True) as session:
            print("started", session.profile_id)

asyncio.run(main())
```

Playwright composition (Playwright outermost, session next, attachment innermost) is shown in
[examples/sync_playwright.py](examples/sync_playwright.py) and
[examples/async_playwright.py](examples/async_playwright.py).

## Ownership warning

`profile_session` requires a literal `exclusive=True` because the session **owns the profile**:
it starts it and stops it when the block ends, including on errors and (async) cancellation.
Do not use it on a profile you are working in by hand, or that another script is driving.

The lock behind it is an in-memory lock inside one Python process. It is not distributed:
another process, another machine or the GPM window can still start or stop the same profile.
It also does not prove the browser was stopped before you started. If a start request times out,
the browser state is unknown (`state_uncertain=True`); the SDK neither retries nor stops it, so
check it yourself.

## More

- [docs/usage.md](docs/usage.md): configuration, error handling, pagination, pitfalls.
- [docs/api.md](docs/api.md): signatures and the endpoint table.
- [docs/compatibility.md](docs/compatibility.md): what is documented, mocked and verified live.
