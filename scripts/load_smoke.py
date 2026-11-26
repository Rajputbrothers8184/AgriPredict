#!/usr/bin/env python3
"""Load smoke test: is the API merely correct, or also usable under load?

This is not a benchmark and it does not try to find a capacity ceiling. It
answers one question a demo cannot: **does latency stay sane and do concurrent
writes stay consistent?** Two failure modes it is designed to catch:

* a query that is fine once and pathological at N+1 (the finance overview
  aggregates several tables per crop cycle);
* a lost update — two concurrent expense writes producing a total that does not
  equal the sum of the parts.

Method
------
A small pool of worker threads issues sequential requests against a fixed set of
pre-created crop cycles, so setup cost is excluded from the numbers. Report
percentiles at p50/p95/p99 rather than a mean: an average hides the tail that
users actually notice.

Usage
-----
    python scripts/load_smoke.py                       # 4 threads, 20 s
    python scripts/load_smoke.py --threads 8 --seconds 60
    python scripts/load_smoke.py --base-url https://api.example.com

The script creates one throwaway account, so it is safe to run against any
environment. It never deletes data.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request

ENDPOINTS = [
    ("GET", "/markets/commodities", "reference data (cacheable, hot path)"),
    ("GET", "/markets/history/wheat/lahore-sabzi-mandi", "91-point price series"),
    ("GET", "/finance/summary", "multi-table aggregate"),
    ("GET", "/crop-cycles", "list with derived finance per row"),
    ("GET", "/reports", "paginated list"),
    ("GET", "/auth/me", "authenticated trivial read"),
]


class Client:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token: str | None = None
        self.local = threading.local()

    def request(self, method: str, path: str, body: dict | None = None):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            status = exc.code
        elapsed = time.perf_counter() - started
        parsed = json.loads(payload) if payload[:1] in (b"{", b"[") else payload
        return status, parsed, elapsed


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int(len(ordered) * fraction), len(ordered) - 1)
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--email", default=None, help="existing account to reuse")
    parser.add_argument("--password", default="LoadSmoke2026")
    args = parser.parse_args()

    client = Client(args.base_url)

    # --- setup: one account, a few cycles to read and write against ----------
    email = args.email or f"load.{int(time.time())}.{random.randint(1000, 9999)}@agripredict-load.pk"
    status, body, _ = client.request(
        "POST",
        "/auth/register",
        {"email": email, "password": args.password, "full_name": "Load Smoke"},
    )
    if status not in (200, 201):
        if status == 429:
            print("error: rate limited during setup; wait a minute and retry", file=sys.stderr)
            return 1
        print(f"error: registration failed {status}: {body}", file=sys.stderr)
        return 1
    client.token = body["access_token"]

    status, commodities, _ = client.request("GET", "/markets/commodities")
    if status != 200 or not commodities:
        print("error: reference data is empty; seed the database first", file=sys.stderr)
        return 1
    commodity_id = commodities[0]["id"]

    status, farm, _ = client.request(
        "POST", "/farms", {"name": "Load Farm", "district": "Lahore", "total_area_acres": 20}
    )
    if status not in (200, 201):
        print(f"error: could not create a farm: {status}", file=sys.stderr)
        return 1

    cycles = []
    for index in range(4):
        status, cycle, _ = client.request(
            "POST",
            "/crop-cycles",
            {
                "farm_id": farm["id"],
                "commodity_id": commodity_id,
                "area_acres": 5,
                "sowing_date": "2026-11-01",
            },
        )
        if status in (200, 201):
            cycles.append(cycle)
    if not cycles:
        print("error: could not create any crop cycles", file=sys.stderr)
        return 1
    print(f"setup: {len(cycles)} cycles for {email}")

    # --- latency sweep -------------------------------------------------------
    results: dict[str, list[float]] = {name: [] for _, _, name in ENDPOINTS}
    errors: list[str] = []
    stop = time.time() + args.seconds
    lock = threading.Lock()

    def worker(worker_id: int) -> None:
        rng = random.Random(worker_id)
        local_results: dict[str, list[float]] = {name: [] for _, _, name in ENDPOINTS}
        local_errors: list[str] = []
        while time.time() < stop:
            method, path, name = rng.choice(ENDPOINTS)
            status, _, elapsed = client.request(method, path)
            if status == 200:
                local_results[name].append(elapsed)
            elif status != 429:
                local_errors.append(f"{method} {path} -> {status}")
        with lock:
            for name, values in local_results.items():
                results[name].extend(values)
            errors.extend(local_errors)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(args.threads)]
    print(f"driving {args.threads} threads for {args.seconds:.0f}s ...")
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall = time.perf_counter() - started

    total = sum(len(v) for v in results.values())
    print(f"\n{total} successful requests in {wall:.1f}s = {total / wall:.1f} req/s\n")
    print(f"{'endpoint':42s} {'n':>6s} {'p50':>7s} {'p95':>7s} {'p99':>7s} {'max':>7s}")
    print("-" * 82)
    worst_p95 = 0.0
    for _, _, name in ENDPOINTS:
        values = results[name]
        if not values:
            print(f"{name:42s} {'0':>6s}   (no successful samples)")
            continue
        p95 = percentile(values, 0.95)
        worst_p95 = max(worst_p95, p95)
        print(
            f"{name:42s} {len(values):6d} "
            f"{percentile(values, 0.50) * 1000:6.0f}ms "
            f"{p95 * 1000:6.0f}ms "
            f"{percentile(values, 0.99) * 1000:6.0f}ms "
            f"{max(values) * 1000:6.0f}ms"
        )

    # --- consistency: concurrent expense writes must not lose updates --------
    target = cycles[0]
    # All writes land on the same cycle: that is where a lost update would show.
    amounts = [100 * n for n in range(1, 41)]  # 40 writes, 8200 PKR in total

    write_errors: list[str] = []

    def writer(chunk: list[int]) -> None:
        for amount in chunk:
            status, _, _ = client.request(
                "POST",
                f"/crop-cycles/{target['id']}/expenses",
                {"category": "labour", "amount_pkr": amount, "expense_date": "2026-11-10"},
            )
            if status not in (200, 201):
                write_errors.append(f"expense {amount} -> {status}")

    chunks = [amounts[i::4] for i in range(4)]  # interleaved, so writers overlap
    writers = [threading.Thread(target=writer, args=(chunk,)) for chunk in chunks if chunk]
    for thread in writers:
        thread.start()
    for thread in writers:
        thread.join()

    status, cycle, _ = client.request("GET", f"/crop-cycles/{target['id']}")
    recorded = -1.0
    if status == 200 and isinstance(cycle, dict):
        # GET /crop-cycles/{id} attaches a derived finance block; cost_pkr is the
        # cost side of it (revenue/cost/profit/margin/yield/break-even).
        finance = cycle.get("finance") or {}
        recorded = float(finance.get("cost_pkr", -1.0))
    expected = float(sum(amounts))
    print(
        f"\nconcurrency: {len(amounts)} expenses written by {len(writers)} threads to one cycle; "
        f"recorded cost {recorded:.2f} vs expected {expected:.2f}"
    )
    if recorded < 0:
        print("error: could not read the cycle finance block; the schema changed")

    failures = []
    if errors:
        failures.append(f"{len(errors)} request errors (e.g. {errors[:3]})")
    if write_errors:
        failures.append(f"{len(write_errors)} write errors ({write_errors[:3]})")
    if abs(recorded - expected) > 0.01:
        failures.append(f"lost update: {recorded:.0f} != {expected:.0f}")
    if worst_p95 > 1.0:
        failures.append(f"p95 latency {worst_p95 * 1000:.0f}ms exceeds 1000ms")

    print()
    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print("PASS  no errors, no lost updates, every p95 under 1000 ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
