#!/usr/bin/env python3
"""
Olist regression guard: byte-for-byte comparison of the Olist demo API responses.

The Olist experience must stay unchanged while dataset-aware features are added.
This script fetches each Olist endpoint and compares the raw response bytes with
the snapshot saved in backend/tests/snapshots/olist_before/.

Usage:
  python scripts/diff_olist_snapshots.py --save            # capture the baseline
  python scripts/diff_olist_snapshots.py                   # compare (exit 1 on any difference)
  python scripts/diff_olist_snapshots.py --base http://127.0.0.1:8001

Base URL: --base, else $INSIGHTFORGE_API_BASE, else http://127.0.0.1:8000.
Requires a running backend connected to the live (non-fixture) Olist database.
"""

import argparse
import difflib
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = ROOT / "backend" / "tests" / "snapshots" / "olist_before"

# snapshot file name -> path (relative to base URL)
ENDPOINTS = {
    "kpis": "/api/kpis",
    "analytics_revenue_trend": "/api/analytics/revenue-trend",
    "analytics_categories": "/api/analytics/categories",
    "analytics_states": "/api/analytics/states",
    "analytics_sellers": "/api/analytics/sellers",
    "analytics_payments": "/api/analytics/payments",
    "analytics_delivery": "/api/analytics/delivery",
    "data_quality": "/api/data-quality",
    "anomalies": "/api/anomalies",
}


def fetch(client: httpx.Client, path: str) -> bytes:
    res = client.get(path)
    if res.status_code != 200:
        raise RuntimeError(f"{path} returned HTTP {res.status_code}: {res.text[:200]}")
    return res.content


def pretty(raw: bytes) -> list:
    try:
        return json.dumps(json.loads(raw), indent=2, sort_keys=True, ensure_ascii=False).splitlines()
    except ValueError:
        return raw.decode("utf-8", "replace").splitlines()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=os.getenv("INSIGHTFORGE_API_BASE", "http://127.0.0.1:8000"))
    ap.add_argument("--save", action="store_true", help="write a new baseline instead of comparing")
    ap.add_argument("--timeout", type=float, default=120.0)
    args = ap.parse_args()

    with httpx.Client(base_url=args.base, timeout=args.timeout) as client:
        health = client.get("/api/health").json()
        if health.get("data_source") != "postgres":
            print(f"Refusing to run: backend data_source={health.get('data_source')!r}, need the live 'postgres' database.")
            return 2

        if args.save:
            SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
            for name, path in ENDPOINTS.items():
                raw = fetch(client, path)
                (SNAPSHOT_DIR / f"{name}.json").write_bytes(raw)
                print(f"saved  {name:28s} {len(raw):>8} bytes  {path}")
            return 0

        if not SNAPSHOT_DIR.exists():
            print(f"No baseline at {SNAPSHOT_DIR}. Run with --save first.")
            return 2

        failures = 0
        for name, path in ENDPOINTS.items():
            before = (SNAPSHOT_DIR / f"{name}.json").read_bytes()
            after = fetch(client, path)
            if before == after:
                print(f"same   {name:28s} {len(after):>8} bytes  {path}")
                continue
            failures += 1
            print(f"DIFF   {name:28s} {path}")
            for line in list(difflib.unified_diff(pretty(before), pretty(after), "before", "after", lineterm=""))[:60]:
                print("    " + line)

        print(f"\n{len(ENDPOINTS) - failures}/{len(ENDPOINTS)} Olist endpoints byte-for-byte identical")
        return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
