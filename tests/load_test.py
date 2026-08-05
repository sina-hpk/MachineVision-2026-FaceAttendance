"""
Python Load Test — runs without k6.
Tests concurrent request handling performance.

Usage:
    python tests/load_test.py
    python tests/load_test.py --base-url http://localhost:8000 --concurrency 20 --requests 100
"""
import argparse
import time
import statistics
import threading
import urllib.request
import urllib.error
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin


ENDPOINTS = [
    ("GET", "/healthz", 200),
    ("GET", "/api/dashboard", 200),
    ("GET", "/api/attendance/report", 200),
    ("GET", "/camera/status", 200),
    ("GET", "/metrics", 200),
    ("GET", "/auth/me", 401),
    ("GET", "/workers", 401),
    ("POST", "/auth/login", 401, {"username": "x", "password": "x"}),
]


class StatsCollector:
    def __init__(self):
        self.lock = threading.Lock()
        self.results = []

    def add(self, endpoint: str, status: int, expected: int, duration: float, ok: bool):
        with self.lock:
            self.results.append({
                "endpoint": endpoint,
                "status": status,
                "expected": expected,
                "duration": duration,
                "ok": ok,
            })

    def report(self):
        by_endpoint = {}
        for r in self.results:
            by_endpoint.setdefault(r["endpoint"], []).append(r["duration"])

        total = len(self.results)
        ok_count = sum(1 for r in self.results if r["ok"])
        print(f"\n{'='*50}")
        print(f"RESULTS: {ok_count}/{total} passed ({ok_count/total*100:.1f}%)")
        print(f"{'='*50}")

        for ep, durs in sorted(by_endpoint.items()):
            if not durs:
                continue
            avg = statistics.mean(durs)
            p50 = statistics.median(durs)
            p95 = sorted(durs)[int(len(durs) * 0.95)]
            p99 = sorted(durs)[int(len(durs) * 0.99)]
            max_d = max(durs)
            print(f"\n  {ep}:")
            print(f"    Count: {len(durs)}")
            print(f"    Avg:   {avg*1000:.1f}ms")
            print(f"    P50:   {p50*1000:.1f}ms")
            print(f"    P95:   {p95*1000:.1f}ms")
            print(f"    P99:   {p99*1000:.1f}ms")
            print(f"    Max:   {max_d*1000:.1f}ms")


def hit_endpoint(base_url: str, method: str, path: str, expected: int, body: dict | None, stats: StatsCollector):
    url = urljoin(base_url, path)
    start = time.time()
    try:
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method)
        if body:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception as e:
        stats.add(path, 0, expected, time.time() - start, False)
        return

    duration = time.time() - start
    ok = status == expected
    stats.add(path, status, expected, duration, ok)


def run_concurrent(base_url: str, concurrency: int, total_requests: int):
    stats = StatsCollector()
    tasks = []

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for _ in range(total_requests):
            # Pick a random endpoint
            ep = ENDPOINTS[_ % len(ENDPOINTS)]
            method, path, expected = ep[0], ep[1], ep[2]
            body = ep[3] if len(ep) > 3 else None
            tasks.append(
                executor.submit(hit_endpoint, base_url, method, path, expected, body, stats)
            )

        for f in as_completed(tasks):
            f.result()  # Propagate exceptions

    stats.report()
    return stats


def main():
    parser = argparse.ArgumentParser(description="Load test for CV Attendance System")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent users")
    parser.add_argument("--requests", type=int, default=50, help="Total requests")
    args = parser.parse_args()

    print(f"Load Test: {args.base_url}")
    print(f"Concurrency: {args.concurrency}, Total Requests: {args.requests}")
    print(f"{'='*50}")

    start = time.time()
    run_concurrent(args.base_url, args.concurrency, args.requests)
    elapsed = time.time() - start
    print(f"\nTotal time: {elapsed:.2f}s")
    print(f"Throughput: {args.requests / elapsed:.1f} req/s")


if __name__ == "__main__":
    main()
