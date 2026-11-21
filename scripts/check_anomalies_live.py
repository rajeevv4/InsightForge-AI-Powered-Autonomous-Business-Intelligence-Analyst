#!/usr/bin/env python3
"""
InsightForge — Real PostgreSQL Live Anomaly Detection Scanner
============================================================
Executes deterministic anomaly detection against REAL PostgreSQL tables/views.
Fixtures are strictly disabled (USE_FIXTURES=0).
If the database is unreachable, prints a clear diagnostic message and exits.
"""

import os
import sys
from pathlib import Path

# Strictly enforce real database execution (NO fixtures allowed)
os.environ["USE_FIXTURES"] = "0"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from backend.app.database import readonly_engine
from backend.app.services.anomaly_service import AnomalyService
from backend.app.exceptions import DatabaseUnavailableError


def check_database_connection() -> bool:
    """Verifies physical database connectivity before executing scan."""
    try:
        with readonly_engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
        return True
    except Exception as e:
        return False


def main():
    print("=" * 86)
    print("       INSIGHTFORGE — REAL POSTGRESQL LIVE ANOMALY DETECTION SCANNER")
    print("=" * 86)
    print("Configuration: USE_FIXTURES=0 (Real PostgreSQL Database Mode Only)")

    # 1. Verify PostgreSQL is live
    if not check_database_connection():
        print("\n❌ DATABASE UNREACHABLE")
        print("Could not connect to PostgreSQL via readonly_engine.")
        print("Please ensure PostgreSQL is running, listening on port 5432, and configured in .env.")
        print("Exiting.\n")
        sys.exit(1)

    print(" Database connection established successfully.")
    print("Running multi-method anomaly scan across daily delivered order metrics...\n")

    try:
        # 2. Run live anomaly scan
        scan_response = AnomalyService.run_full_scan(
            metrics=["gross_revenue", "order_count", "aov", "on_time_delivery_rate", "avg_review_score"],
            grain="daily"
        )
    except DatabaseUnavailableError as e:
        print(f"\n❌ Database error during scan: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error during scan: {e}")
        sys.exit(1)

    anomalies = scan_response.anomalies
    print(f"Total Anomalies Detected: {len(anomalies)}")
    print(f"High Severity Anomalies:  {scan_response.high_severity_count}")
    print("-" * 86)
    print(f"{'#':<3} | {'Period':<10} | {'Metric':<18} | {'Observed':<14} | {'Expected':<12} | {'Score':<6} | {'Sev':<6} | {'Method':<14} | {'Event'}")
    print("-" * 86)

    top_10 = anomalies[:10]
    for idx, a in enumerate(top_10, 1):
        obs_str = f"R$ {a.observed:,.2f}" if "revenue" in a.metric or "aov" in a.metric else f"{a.observed:,.2f}"
        exp_str = f"R$ {a.expected:,.2f}" if "revenue" in a.metric or "aov" in a.metric else f"{a.expected:,.2f}"
        ev_str = a.known_event_candidate or "—"

        print(
            f"{idx:<3} | {a.period:<10} | {a.metric:<18} | {obs_str:<14} | {exp_str:<12} | "
            f"{a.deviation_score:<6.2f} | {a.severity:<6} | {a.method:<14} | {ev_str}"
        )

    print("=" * 86)
    print(" Live scan completed successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()
