"""
Live regression: the Olist demo API must stay byte-for-byte identical to the saved baseline.

Runs scripts/diff_olist_snapshots.py against a running backend that is connected to the
live Olist database. Base URL: $INSIGHTFORGE_API_BASE (default http://127.0.0.1:8000).
Skipped when no such backend is reachable.

Run: INSIGHTFORGE_API_BASE=http://127.0.0.1:8001 python -m unittest backend.tests_integration.test_olist_snapshots_live
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
BASE = os.getenv("INSIGHTFORGE_API_BASE", "http://127.0.0.1:8000")


class TestOlistSnapshotsLive(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            health = httpx.get(f"{BASE}/api/health", timeout=10).json()
        except Exception as e:
            raise unittest.SkipTest(f"No backend reachable at {BASE}: {e}")
        if health.get("data_source") != "postgres":
            raise unittest.SkipTest(f"Backend at {BASE} is not on the live Olist database.")

    def test_zero_differences(self):
        script = ROOT / "scripts" / "diff_olist_snapshots.py"
        for attempt in range(2):  # one retry for a transient upstream 5xx (e.g. cold statement timeout)
            proc = subprocess.run([sys.executable, str(script), "--base", BASE], capture_output=True, text=True, timeout=900)
            if proc.returncode == 0 or "returned HTTP 5" not in proc.stdout + proc.stderr:
                break
        self.assertEqual(proc.returncode, 0, proc.stdout[-3000:] + proc.stderr[-1000:])
        self.assertIn("9/9 Olist endpoints byte-for-byte identical", proc.stdout)


if __name__ == "__main__":
    unittest.main()
