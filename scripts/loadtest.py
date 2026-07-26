#!/usr/bin/env python3
"""Tiny async load test for the gateway (uses httpx, already a backend dep).

Fires N requests at /api/chat with a bounded concurrency and reports throughput,
latency percentiles, and the status-code mix (429s show rate-limiting kicking in).
Combine with the demo fault-injection opts for a chaos test — e.g. force provider
errors and confirm failover holds under load.

Usage:
  python scripts/loadtest.py --base http://localhost:8000 -n 200 -c 20
  python scripts/loadtest.py -n 100 -c 10 --prompt "summarize the OWASP LLM top 10"
"""

from __future__ import annotations

import argparse
import asyncio
import time

import httpx


async def _one(client: httpx.AsyncClient, url: str, prompt: str) -> tuple[int, float]:
    t0 = time.perf_counter()
    try:
        async with client.stream("POST", url, json={"prompt": prompt}) as r:
            async for _ in r.aiter_bytes():
                pass
            status = r.status_code
    except Exception:
        status = 0  # connection/timeout error
    return status, (time.perf_counter() - t0) * 1000


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("-n", "--requests", type=int, default=100)
    ap.add_argument("-c", "--concurrency", type=int, default=10)
    ap.add_argument("--prompt", default="hello there, how are you?")
    args = ap.parse_args()

    url = f"{args.base}/api/chat"
    sem = asyncio.Semaphore(args.concurrency)
    latencies: list[float] = []
    statuses: dict[int, int] = {}

    async with httpx.AsyncClient(timeout=30) as client:
        async def run_one():
            async with sem:
                status, ms = await _one(client, url, args.prompt)
                latencies.append(ms)
                statuses[status] = statuses.get(status, 0) + 1

        wall0 = time.perf_counter()
        await asyncio.gather(*(run_one() for _ in range(args.requests)))
        wall = time.perf_counter() - wall0

    latencies.sort()

    def pct(p: float) -> float:
        if not latencies:
            return 0.0
        return latencies[min(len(latencies) - 1, int(len(latencies) * p))]

    print(f"requests={args.requests} concurrency={args.concurrency} wall={wall:.2f}s")
    print(f"throughput={args.requests / wall:.1f} req/s")
    print(f"latency ms: p50={pct(0.5):.0f} p95={pct(0.95):.0f} p99={pct(0.99):.0f} max={latencies[-1]:.0f}")
    print(f"status mix: {dict(sorted(statuses.items()))}  (429 = rate-limited, 0 = error)")


if __name__ == "__main__":
    asyncio.run(main())
