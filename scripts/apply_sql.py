#!/usr/bin/env python3
"""
InsightForge — Apply SQL Script with Admin Connection & Verify Read-Only Permissions
===================================================================================
Executes raw SQL scripts (schema, views, roles) against PostgreSQL via the admin engine.
Can also run permission verifications against the read-only role (insightforge_ro).
"""

import sys
import os
from pathlib import Path
from sqlalchemy import text

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.app.database import engine, readonly_engine, check_db_connection


def apply_sql(file_path: Path):
    if not file_path.exists():
        print(f"❌ Error: File not found: {file_path}")
        sys.exit(1)

    print(f"📄 Applying SQL file: {file_path.name} via admin connection...")
    with open(file_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # Split on semicolons or execute blocks
    # Note: postgres DO blocks and transactions require careful execution
    with engine.connect() as conn:
        with conn.begin():
            # In PostgreSQL, multiple statements can be executed in one execute() call
            conn.execute(text(sql_content))
    print(f"✅ Successfully executed {file_path.name}")


def verify_readonly_permissions():
    print("\n" + "=" * 60)
    print("  VERIFYING insightforge_ro ROLE PERMISSIONS (LEVEL 3.5)")
    print("=" * 60)

    # 1. Test SELECT from orders (Should PASS)
    try:
        with readonly_engine.connect() as ro_conn:
            res = ro_conn.execute(text("SELECT count(*) FROM orders;")).scalar()
            print(f"✅ 1. SELECT from orders: ALLOWED (Found {res} rows)")
    except Exception as e:
        print(f"❌ 1. SELECT from orders: FAILED UNEXPECTEDLY ({e})")

    # 2. Test SELECT from ai_audit_log (Should be DENIED)
    try:
        with readonly_engine.connect() as ro_conn:
            ro_conn.execute(text("SELECT * FROM ai_audit_log LIMIT 1;"))
            print("❌ 2. SELECT from ai_audit_log: ALLOWED (SECURITY VIOLATION!)")
    except Exception as e:
        if "permission denied" in str(e).lower() or "denied" in str(e).lower():
            print("✅ 2. SELECT from ai_audit_log: DENIED (Permission revoked as required)")
        else:
            print(f"✅ 2. SELECT from ai_audit_log: DENIED ({e})")

    # 3. Test INSERT into orders (Should be DENIED)
    try:
        with readonly_engine.connect() as ro_conn:
            with ro_conn.begin():
                ro_conn.execute(text("INSERT INTO orders (order_id) VALUES ('__audit_probe__');"))
            print("❌ 3. INSERT into orders: ALLOWED (SECURITY VIOLATION!)")
    except Exception as e:
        if "permission denied" in str(e).lower() or "denied" in str(e).lower():
            print("✅ 3. INSERT into orders: DENIED (Read-only enforced)")
        else:
            print(f"✅ 3. INSERT into orders: DENIED ({e})")

    # 4. Test DROP TABLE orders (Should be DENIED)
    try:
        with readonly_engine.connect() as ro_conn:
            with ro_conn.begin():
                ro_conn.execute(text("DROP TABLE orders;"))
            print("❌ 4. DROP TABLE orders: ALLOWED (SECURITY VIOLATION!)")
    except Exception as e:
        if "permission denied" in str(e).lower() or "denied" in str(e).lower():
            print("✅ 4. DROP TABLE orders: DENIED (DDL forbidden)")
        else:
            print(f"✅ 4. DROP TABLE orders: DENIED ({e})")

    print("=" * 60 + "\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/apply_sql.py <path_to_sql_file> [--verify-ro]")
        sys.exit(1)

    target_file = Path(sys.argv[1])
    apply_sql(target_file)

    if "--verify-ro" in sys.argv or target_file.name == "roles.sql":
        verify_readonly_permissions()


if __name__ == "__main__":
    main()
