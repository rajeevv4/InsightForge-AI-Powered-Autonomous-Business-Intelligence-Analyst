#!/usr/bin/env python3
"""
InsightForge — Dataset Workspace Cleanup Daemon / Script
=========================================================
Finds expired datasets (expires_at < NOW()) in insightforge.datasets,
drops their PostgreSQL schemas (DROP SCHEMA ds_<8hex> CASCADE), and
purges metadata records. Never touches the built-in demo dataset ('olist-demo').
"""

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from psycopg2 import sql
from sqlalchemy import text

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.app.database import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cleanup_datasets")


def cleanup_expired_datasets(dry_run: bool = False) -> int:
    """
    Identifies and purges datasets whose expires_at is in the past.
    Returns the count of purged datasets.
    """
    now = datetime.now(timezone.utc)
    logger.info(f"Checking for expired datasets at {now.isoformat()}...")

    with engine.connect() as conn:
        expired = conn.execute(
            text("""
                SELECT id, name, schema_name, expires_at
                FROM insightforge.datasets
                WHERE expires_at IS NOT NULL
                  AND expires_at < NOW()
                  AND schema_name != 'insightforge';
            """)
        ).fetchall()

    if not expired:
        logger.info("No expired datasets found. Database clean.")
        return 0

    logger.info(f"Found {len(expired)} expired dataset(s) to purge.")

    purged_count = 0
    raw_conn = engine.raw_connection()
    try:
        with raw_conn.cursor() as cur:
            for ds in expired:
                ds_id = str(ds[0])
                ds_name = ds[1]
                schema_name = ds[2]
                exp_at = ds[3]

                logger.info(f"Purging dataset '{ds_name}' (ID: {ds_id}, Schema: {schema_name}, Expired: {exp_at})...")

                if dry_run:
                    logger.info(f"  [DRY RUN] Would DROP SCHEMA {schema_name} CASCADE and DELETE metadata.")
                    purged_count += 1
                    continue

                # 1. Drop schema cascade using Identifier
                cur.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE;").format(
                        sql.Identifier(schema_name)
                    )
                )

                # 2. Delete metadata
                cur.execute(
                    "DELETE FROM insightforge.datasets WHERE id = %s;",
                    (ds_id,)
                )

                # 3. Drop defense-in-depth role
                if schema_name.startswith("ds_"):
                    role_name = f"dsr_{schema_name[3:]}"
                    try:
                        cur.execute(sql.SQL("DROP ROLE IF EXISTS {};").format(sql.Identifier(role_name)))
                    except Exception as e:
                        logger.debug(f"Could not drop role {role_name}: {e}")

                purged_count += 1

        if not dry_run:
            raw_conn.commit()
            logger.info(f"Successfully purged {purged_count} expired dataset(s).")
    except Exception as e:
        raw_conn.rollback()
        logger.error(f"Error during dataset cleanup: {e}", exc_info=True)
        raise
    finally:
        raw_conn.close()

    return purged_count


if __name__ == "__main__":
    is_dry = "--dry-run" in sys.argv
    cleaned = cleanup_expired_datasets(dry_run=is_dry)
    print(f"Cleanup finished: {cleaned} dataset(s) processed.")
