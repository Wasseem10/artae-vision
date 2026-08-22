"""Bounded, read-only concurrency smoke test for a running control plane."""

from __future__ import annotations

import argparse
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def request_once(url: str, timeout_seconds: float) -> tuple[int, float]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            response.read(64)
            status = response.status
    except (OSError, TimeoutError, urllib.error.URLError):
        status = 0
    return status, (time.perf_counter() - started) * 1000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/api/v1/health/ready")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=5)
    args = parser.parse_args()
    if not 1 <= args.requests <= 10_000:
        parser.error("--requests must be between 1 and 10000")
    if not 1 <= args.concurrency <= 100:
        parser.error("--concurrency must be between 1 and 100")

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        results = list(
            executor.map(
                lambda _: request_once(args.url, args.timeout_seconds),
                range(args.requests),
            )
        )
    successful = [latency for status, latency in results if status == 200]
    latencies = sorted(latency for _, latency in results)
    p95_index = min(len(latencies) - 1, int(len(latencies) * 0.95))
    print(
        f"requests={len(results)} success={len(successful)} "
        f"p50_ms={statistics.median(latencies):.1f} p95_ms={latencies[p95_index]:.1f}"
    )
    return 0 if len(successful) == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
