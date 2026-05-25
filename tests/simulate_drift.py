from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Any

import httpx

TRACK_URL = "http://localhost:8000/track"
REQUESTS = 5000
CONCURRENCY = 200


@dataclass
class SimulationResult:
    total: int
    success: int
    failure: int


def payload_variant(i: int) -> dict[str, Any]:
    base: dict[str, Any] = {
        "user_id": i,
        "meta": {"tags": ["admin", "staff"], "active": True},
        "score": 42,
    }
    phase = i % 4
    if phase == 1:
        base["optional"] = None
    elif phase == 2:
        base["score"] = 42.5
    elif phase == 3:
        base.pop("meta")
    return base


async def _submit(client: httpx.AsyncClient, i: int) -> bool:
    body = {
        "service_name": "chaos-client",
        "http_method": "POST",
        "route_path": "/mocked/contracts",
        "payload": payload_variant(i),
    }
    try:
        r = await client.post(TRACK_URL, json=body)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


async def run_simulation() -> SimulationResult:
    sem = asyncio.Semaphore(CONCURRENCY)

    async with httpx.AsyncClient(timeout=15) as client:
        async def bounded(i: int) -> bool:
            async with sem:
                await asyncio.sleep(random.random() * 0.01)
                return await _submit(client, i)

        results = await asyncio.gather(*(bounded(i) for i in range(REQUESTS)))

    success = sum(1 for ok in results if ok)
    return SimulationResult(total=REQUESTS, success=success, failure=REQUESTS - success)


async def main() -> None:
    result = await run_simulation()
    print(f"total={result.total} success={result.success} failure={result.failure}")


if __name__ == "__main__":
    asyncio.run(main())
