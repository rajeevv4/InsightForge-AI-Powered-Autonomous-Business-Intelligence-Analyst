import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import text

from backend.app.config import settings
from backend.app.database import engine

logger = logging.getLogger(__name__)

# In-memory buffer fallback (keeps the last 100 entries for offline testing or when DB is unreachable)
_memory_audit_log: deque = deque(maxlen=100)
_table_initialized: bool = False


class AIAuditService:
    """
    Audit logging service for InsightForge AI requests.
    Tracks queries, classified intents, generated SQL, execution latency, and success/failure status.
    """

    @classmethod
    def _ensure_table(cls):
        global _table_initialized
        if _table_initialized:
            return
        try:
            with engine.connect() as conn:
                conn.execute(text(f"""
                    CREATE SCHEMA IF NOT EXISTS {settings.DB_SCHEMA};
                    CREATE TABLE IF NOT EXISTS {settings.DB_SCHEMA}.ai_audit_log (
                        id SERIAL PRIMARY KEY,
                        question TEXT NOT NULL,
                        intent VARCHAR(100),
                        generated_sql TEXT,
                        latency_ms DOUBLE PRECISION NOT NULL,
                        success BOOLEAN NOT NULL,
                        error TEXT,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_ai_audit_log_timestamp
                        ON {settings.DB_SCHEMA}.ai_audit_log (timestamp DESC);
                """))
                conn.commit()
                _table_initialized = True
        except Exception as e:
            logger.debug(f"Audit log table auto-creation skipped: {e}")

    @classmethod
    def log(
        cls,
        question: str,
        intent: Optional[str],
        generated_sql: Optional[str],
        latency_ms: float,
        success: bool,
        error: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Record an AI interaction event. Writes to PostgreSQL table and in-memory buffer.
        """
        ts = datetime.now(timezone.utc).isoformat()
        entry = {
            "id": len(_memory_audit_log) + 1,
            "question": question,
            "intent": intent,
            "generated_sql": generated_sql,
            "latency_ms": round(latency_ms, 2),
            "success": success,
            "error": error,
            "timestamp": ts
        }

        # Always append to in-memory fallback
        _memory_audit_log.append(entry)

        # Attempt PostgreSQL insert
        try:
            cls._ensure_table()
            with engine.connect() as conn:
                stmt = text(f"""
                    INSERT INTO {settings.DB_SCHEMA}.ai_audit_log
                        (question, intent, generated_sql, latency_ms, success, error, timestamp)
                    VALUES
                        (:question, :intent, :generated_sql, :latency_ms, :success, :error, NOW())
                    RETURNING id, timestamp;
                """)
                res = conn.execute(stmt, {
                    "question": question,
                    "intent": intent,
                    "generated_sql": generated_sql,
                    "latency_ms": latency_ms,
                    "success": success,
                    "error": error
                }).fetchone()
                conn.commit()
                if res:
                    entry["id"] = res[0]
                    entry["timestamp"] = res[1].isoformat() if hasattr(res[1], "isoformat") else str(res[1])
        except Exception as e:
            logger.warning(f"Could not persist AI audit log to database (saved in memory): {e}")

        return entry

    @classmethod
    def get_history(cls, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieve recent AI query history. Queries PostgreSQL first; falls back to in-memory log.
        """
        limit = max(1, min(limit, 500))

        # Try database retrieval
        try:
            cls._ensure_table()
            with engine.connect() as conn:
                stmt = text(f"""
                    SELECT id, question, intent, generated_sql, latency_ms, success, error, timestamp
                    FROM {settings.DB_SCHEMA}.ai_audit_log
                    ORDER BY timestamp DESC
                    LIMIT :limit;
                """)
                rows = conn.execute(stmt, {"limit": limit}).fetchall()
                if rows:
                    return [
                        {
                            "id": r[0],
                            "question": r[1],
                            "intent": r[2],
                            "generated_sql": r[3],
                            "latency_ms": float(r[4]),
                            "success": bool(r[5]),
                            "error": r[6],
                            "timestamp": r[7].isoformat() if hasattr(r[7], "isoformat") else str(r[7])
                        }
                        for r in rows
                    ]
        except Exception as e:
            logger.debug(f"Database audit history fetch failed, using memory cache: {e}")

        # Fallback to in-memory log
        entries = list(_memory_audit_log)
        entries.reverse()
        return entries[:limit]

    @classmethod
    def clear_memory(cls):
        """Helper for test isolation."""
        _memory_audit_log.clear()
