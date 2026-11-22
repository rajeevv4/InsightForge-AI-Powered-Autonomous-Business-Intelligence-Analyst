import hashlib
import io
import json
import logging
import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import psycopg2
from psycopg2 import sql
from sqlalchemy import text

from backend.app.config import settings
from backend.app.database import engine, readonly_engine, check_db_connection
from backend.app.exceptions import DatabaseUnavailableError
from backend.app.fixture_guard import is_fixture_mode
from backend.app.schemas.dataset import (
    ColumnProfile,
    DatasetProfile,
    DatasetSummary,
    RelationshipProfile,
    TablePreviewResponse,
    TableProfile,
    UploadDatasetResponse,
)
from backend.app.services.audit_service import AIAuditService
from backend.app.services.dataset_file_parser import DatasetFileParser, FileValidationError
from backend.app.services.dataset_profiler import DatasetProfiler

logger = logging.getLogger(__name__)

DEMO_DATASET_ID = "00000000-0000-0000-0000-000000000001"
DEMO_SCHEMA_NAME = "insightforge"


def hash_token(token: str) -> str:
    """Computes SHA-256 hash of owner token."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


class DatasetService:
    """
    Manages multi-tenant dataset workspace: safe upload, COPY ingestion,
    schema isolation, deterministic profiling, and lifecycle management.
    """

    @classmethod
    def _assert_live_db(cls):
        """Rule 5: Fail fast if in offline fixture mode."""
        if is_fixture_mode():
            raise DatabaseUnavailableError(
                "Dataset upload and management requires a live PostgreSQL connection. "
                "Offline fixture mode (USE_FIXTURES=1) cannot host dynamic datasets."
            )

    @classmethod
    def check_database_storage_capacity(cls) -> Tuple[float, float]:
        """
        Queries current database size and validates against MAX_TOTAL_DB_MB.
        Returns (current_mb, max_mb). Raises FileValidationError if capacity exceeded.
        """
        with engine.connect() as conn:
            size_bytes = conn.execute(text("SELECT pg_database_size(current_database());")).scalar() or 0

        current_mb = size_bytes / (1024 * 1024)
        max_mb = float(settings.MAX_TOTAL_DB_MB)

        if current_mb >= max_mb:
            raise FileValidationError(
                f"Database storage capacity limit reached (current usage: {current_mb:.1f} MB, "
                f"limit: {max_mb:.1f} MB). Please delete expired datasets before uploading new files.",
                status_code=507
            )
        return current_mb, max_mb

    @classmethod
    def count_owner_datasets(cls, owner_token_hash: str) -> int:
        """Counts existing active datasets for an owner token hash."""
        with engine.connect() as conn:
            cnt = conn.execute(
                text("SELECT count(*) FROM insightforge.datasets WHERE owner_token_hash = :hash AND schema_name != 'insightforge';"),
                {"hash": owner_token_hash}
            ).scalar()
        return cnt or 0

    @classmethod
    def count_global_datasets(cls) -> int:
        """Counts total active uploaded datasets across all owners."""
        with engine.connect() as conn:
            cnt = conn.execute(
                text("SELECT count(*) FROM insightforge.datasets WHERE schema_name != 'insightforge';")
            ).scalar()
        return cnt or 0

    @classmethod
    def count_daily_ip_uploads(cls, client_ip: str) -> int:
        """Counts datasets uploaded by client_ip in the past 24 hours from the audit log."""
        if not client_ip:
            return 0
        with engine.connect() as conn:
            cnt = conn.execute(
                text("""
                    SELECT count(*) FROM insightforge.ai_audit_log
                    WHERE intent = 'dataset_upload'
                      AND question LIKE :pattern
                      AND timestamp > NOW() - INTERVAL '24 hours'
                      AND success = true;
                """),
                {"pattern": f"%ip: {client_ip}%"}
            ).scalar()
        return cnt or 0

    @classmethod
    def upload_dataset(
        cls,
        files_data: List[Tuple[str, bytes]],
        owner_token: Optional[str] = None,
        dataset_name: Optional[str] = None,
        client_ip: Optional[str] = None
    ) -> UploadDatasetResponse:
        """
        Loads 1-5 tabular files into a dedicated PostgreSQL schema (ds_<8hex>).
        Executes ingestion in a single transaction with COPY and quoted identifiers.
        On any failure drops schema and rollback metadata.
        """
        cls._assert_live_db()

        if not files_data:
            raise FileValidationError("No files uploaded. Please provide 1-5 CSV, TSV, or XLSX files.", status_code=400)
        if len(files_data) > 5:
            raise FileValidationError("Exceeded maximum of 5 files per dataset upload.", status_code=400)

        # 1. Check database capacity & global limits
        cls.check_database_storage_capacity()

        global_dataset_count = cls.count_global_datasets()
        if global_dataset_count >= settings.MAX_GLOBAL_DATASETS:
            raise FileValidationError(
                f"Global dataset limit reached ({global_dataset_count}/{settings.MAX_GLOBAL_DATASETS}). System capacity full.",
                status_code=507
            )

        # 2. Check per-IP daily upload limit
        if client_ip:
            daily_ip_count = cls.count_daily_ip_uploads(client_ip)
            if daily_ip_count >= settings.MAX_DATASETS_PER_IP_PER_DAY:
                raise FileValidationError(
                    f"Daily upload limit of {settings.MAX_DATASETS_PER_IP_PER_DAY} datasets per IP exceeded.",
                    status_code=429
                )

        # 3. Owner token resolution
        issued_new_token = False
        if not owner_token or not owner_token.strip():
            owner_token = f"own_{secrets.token_hex(16)}"
            issued_new_token = True

        owner_hash = hash_token(owner_token)

        # 3. Check owner dataset limit
        owner_dataset_count = cls.count_owner_datasets(owner_hash)
        if owner_dataset_count >= settings.MAX_DATASETS_PER_OWNER:
            raise FileValidationError(
                f"Owner dataset quota exceeded. Maximum {settings.MAX_DATASETS_PER_OWNER} datasets allowed per owner. "
                "Please delete an existing dataset to upload a new one.",
                status_code=400
            )

        # 4. Generate unique dataset and schema identifiers
        dataset_id = str(uuid.uuid4())
        short_id = uuid.uuid4().hex[:8]
        schema_name = f"ds_{short_id}"

        clean_dataset_name = dataset_name.strip() if dataset_name and dataset_name.strip() else Path(files_data[0][0]).stem.replace("_", " ").title()

        source_file_names = [f[0] for f in files_data]
        total_upload_bytes = sum(len(f[1]) for f in files_data)

        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.DATASET_EXPIRY_HOURS)

        parsed_tables: Dict[str, Tuple[pd.DataFrame, TableProfile, Dict[str, str]]] = {}
        used_table_names: Set[str] = set()

        import tempfile

        # Process each file to DataFrame and initial profile
        for filename, file_bytes in files_data:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
                tmp_path = Path(tmp.name)
                tmp.write(file_bytes)

            try:
                df, safe_tbl, safe_cols, col_mapping, warnings = DatasetFileParser.parse_to_dataframe(tmp_path, filename)

                # Ensure unique table names within schema
                orig_tbl_name = safe_tbl
                ctr = 1
                while safe_tbl in used_table_names:
                    safe_tbl = f"{orig_tbl_name}_{ctr}"
                    ctr += 1
                used_table_names.add(safe_tbl)

                tbl_profile = DatasetProfiler.profile_dataframe(
                    df=df,
                    original_table_name=filename,
                    safe_table_name=safe_tbl,
                    column_mapping=col_mapping,
                    share_samples=False
                )
                if warnings:
                    tbl_profile.quality_findings.extend(warnings)

                parsed_tables[safe_tbl] = (df, tbl_profile, col_mapping)
            finally:
                if tmp_path.exists():
                    os.unlink(tmp_path)

        # Infer relationships across tables if multi-file
        tables_data_dict = {tbl: data[0] for tbl, data in parsed_tables.items()}
        tables_profiles_dict = {tbl: data[1] for tbl, data in parsed_tables.items()}
        inferred_relationships = DatasetProfiler.infer_relationships(tables_data_dict, tables_profiles_dict)

        # 5. Ingest in ONE transaction via psycopg2 raw connection for COPY support
        raw_conn = engine.raw_connection()
        try:
            with raw_conn.cursor() as cur:
                # A. Create Schema and Grant Permissions to insightforge_ro
                cur.execute(sql.SQL("CREATE SCHEMA {};").format(sql.Identifier(schema_name)))
                cur.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO insightforge_ro;").format(sql.Identifier(schema_name)))
                cur.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT SELECT ON TABLES TO insightforge_ro;").format(sql.Identifier(schema_name)))

                # Defense-in-depth: dedicated NOLOGIN role for this dataset schema
                role_name = f"dsr_{schema_name[3:]}" if schema_name.startswith("ds_") else f"dsr_{dataset_hex}"
                try:
                    cur.execute(sql.SQL("CREATE ROLE {} NOLOGIN;").format(sql.Identifier(role_name)))
                    cur.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {};").format(sql.Identifier(schema_name), sql.Identifier(role_name)))
                    cur.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT SELECT ON TABLES TO {};").format(sql.Identifier(schema_name), sql.Identifier(role_name)))
                    cur.execute(sql.SQL("GRANT {} TO insightforge_ro;").format(sql.Identifier(role_name)))
                except Exception as e:
                    logger.warning(f"Could not create defense-in-depth role {role_name}: {e}")

                total_rows_inserted = 0

                # B. Create tables and COPY data
                for safe_tbl, (df, tbl_profile, col_mapping) in parsed_tables.items():
                    col_defs = []
                    col_names = []
                    for c in tbl_profile.columns:
                        col_names.append(sql.Identifier(c.safe_name))
                        col_defs.append(sql.SQL("{} {}").format(sql.Identifier(c.safe_name), sql.SQL(c.pg_type)))

                    create_table_sql = sql.SQL("CREATE TABLE {}.{} ({});").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(safe_tbl),
                        sql.SQL(", ").join(col_defs)
                    )
                    cur.execute(create_table_sql)

                    # Stream data via copy_expert
                    csv_buffer = io.StringIO()
                    df.to_csv(csv_buffer, index=False, header=True, sep=",", na_rep="")
                    csv_buffer.seek(0)

                    copy_sql = sql.SQL("COPY {}.{} ({}) FROM STDIN WITH (FORMAT csv, HEADER true, DELIMITER ',');").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(safe_tbl),
                        sql.SQL(", ").join(col_names)
                    )
                    cur.copy_expert(copy_sql.as_string(cur), csv_buffer)

                    # Grant SELECT on newly created table to insightforge_ro and dedicated role explicitly
                    cur.execute(sql.SQL("GRANT SELECT ON {}.{} TO insightforge_ro;").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(safe_tbl)
                    ))
                    try:
                        cur.execute(sql.SQL("GRANT SELECT ON {}.{} TO {};").format(
                            sql.Identifier(schema_name),
                            sql.Identifier(safe_tbl),
                            sql.Identifier(role_name)
                        ))
                    except Exception:
                        pass
                    total_rows_inserted += len(df)

                # C. Save Metadata
                cur.execute(
                    """
                    INSERT INTO insightforge.datasets (
                        id, name, owner_token_hash, schema_name, status,
                        share_samples, source_files, size_bytes, created_at, expires_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s);
                    """,
                    (
                        dataset_id,
                        clean_dataset_name,
                        owner_hash,
                        schema_name,
                        "ready",
                        False,
                        json.dumps(source_file_names),
                        total_upload_bytes,
                        expires_at
                    )
                )

                for safe_tbl, (df, tbl_profile, col_mapping) in parsed_tables.items():
                    table_id = str(uuid.uuid4())
                    cur.execute(
                        """
                        INSERT INTO insightforge.dataset_tables (
                            id, dataset_id, original_name, safe_name, row_count,
                            column_count, candidate_pk, candidate_time_column, quality_findings
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (
                            table_id,
                            dataset_id,
                            tbl_profile.original_name,
                            safe_tbl,
                            tbl_profile.row_count,
                            tbl_profile.column_count,
                            tbl_profile.candidate_pk,
                            tbl_profile.candidate_time_column,
                            json.dumps(tbl_profile.quality_findings)
                        )
                    )

                    for col in tbl_profile.columns:
                        col_id = str(uuid.uuid4())
                        cur.execute(
                            """
                            INSERT INTO insightforge.dataset_columns (
                                id, table_id, original_name, safe_name, pg_type,
                                role, null_pct, distinct_count, min_val, max_val,
                                stats, user_description
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                            """,
                            (
                                col_id,
                                table_id,
                                col.original_name,
                                col.safe_name,
                                col.pg_type,
                                col.role,
                                col.null_pct,
                                col.distinct_count,
                                str(col.min_val) if col.min_val is not None else None,
                                str(col.max_val) if col.max_val is not None else None,
                                json.dumps(col.stats),
                                col.user_description
                            )
                        )

                for rel in inferred_relationships:
                    rel_id = str(uuid.uuid4())
                    cur.execute(
                        """
                        INSERT INTO insightforge.dataset_relationships (
                            id, dataset_id, parent_table, parent_column, child_table,
                            child_column, cardinality, confidence, confirmed
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (
                            rel_id,
                            dataset_id,
                            rel.parent_table,
                            rel.parent_column,
                            rel.child_table,
                            rel.child_column,
                            rel.cardinality,
                            rel.confidence,
                            rel.confirmed
                        )
                    )

            raw_conn.commit()
        except Exception as e:
            raw_conn.rollback()
            # Clean up schema on failure
            try:
                with raw_conn.cursor() as cur:
                    cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE;").format(sql.Identifier(schema_name)))
                raw_conn.commit()
            except Exception as clean_err:
                logger.error(f"Failed to clean up schema {schema_name} after failure: {clean_err}")
            raise FileValidationError(f"Failed to ingest dataset into PostgreSQL: {e}", status_code=500)
        finally:
            raw_conn.close()

        # Log upload metadata to audit log
        try:
            ip_info = f", ip: {client_ip}" if client_ip else ""
            AIAuditService.log_interaction(
                question=f"[dataset_upload: {clean_dataset_name}, tables: {len(parsed_tables)}, rows: {total_rows_inserted}, schema: {schema_name}{ip_info}]",
                intent="dataset_upload",
                latency_ms=100.0,
                success=True
            )
        except Exception:
            pass

        return UploadDatasetResponse(
            dataset_id=dataset_id,
            name=clean_dataset_name,
            schema_name=schema_name,
            owner_token=owner_token if issued_new_token else None,
            tables_count=len(parsed_tables),
            total_rows=total_rows_inserted,
            expires_at=expires_at,
            message="Dataset uploaded, loaded, and profiled successfully."
        )

    @classmethod
    def list_datasets(cls, owner_token: Optional[str] = None) -> List[DatasetSummary]:
        """Lists accessible datasets (always includes olist-demo + matching owner datasets)."""
        cls._assert_live_db()
        owner_hash = hash_token(owner_token) if owner_token else ""

        query = text("""
            SELECT 
                d.id, d.name, d.schema_name, d.status, d.share_samples,
                d.size_bytes, d.created_at, d.expires_at,
                COUNT(DISTINCT t.id) AS table_count,
                COALESCE(SUM(t.row_count), 0) AS total_rows
            FROM insightforge.datasets d
            LEFT JOIN insightforge.dataset_tables t ON d.id = t.dataset_id
            WHERE d.schema_name = 'insightforge' OR d.owner_token_hash = :hash
            GROUP BY d.id, d.name, d.schema_name, d.status, d.share_samples, d.size_bytes, d.created_at, d.expires_at
            ORDER BY (d.schema_name = 'insightforge') DESC, d.created_at DESC;
        """)

        with engine.connect() as conn:
            rows = conn.execute(query, {"hash": owner_hash}).fetchall()

        results = []
        for r in rows:
            is_demo = (r.schema_name == "insightforge")
            # If demo dataset has 0 counted tables in metadata, provide real canonical counts
            tbl_cnt = r.table_count if r.table_count > 0 else (7 if is_demo else 0)
            tot_rows = int(r.total_rows) if r.total_rows > 0 else (99441 if is_demo else 0)

            results.append(DatasetSummary(
                id=str(r.id),
                name=r.name,
                schema_name=r.schema_name,
                status=r.status,
                share_samples=r.share_samples,
                table_count=tbl_cnt,
                total_rows=tot_rows,
                size_bytes=int(r.size_bytes),
                created_at=r.created_at,
                expires_at=r.expires_at,
                is_demo=is_demo
            ))
        return results

    @classmethod
    def get_dataset_profile(cls, dataset_id: str, owner_token: Optional[str] = None) -> DatasetProfile:
        """Retrieves full profile for a dataset."""
        cls._assert_live_db()
        owner_hash = hash_token(owner_token) if owner_token else ""

        with engine.connect() as conn:
            ds_row = conn.execute(
                text("SELECT * FROM insightforge.datasets WHERE id = :id OR schema_name = :s_id;"),
                {"id": dataset_id if len(dataset_id) == 36 else "00000000-0000-0000-0000-000000000000", "s_id": dataset_id}
            ).fetchone()

        if not ds_row:
            raise FileValidationError("Dataset not found.", status_code=404)

        is_demo = (ds_row.schema_name == "insightforge")
        if not is_demo and ds_row.owner_token_hash != owner_hash:
            raise FileValidationError("Access denied. Invalid owner token for this dataset.", status_code=403)

        # If Olist demo, generate/return demo profile dynamically if not in tables
        if is_demo:
            return cls._get_olist_demo_profile(ds_row)

        # Query tables, columns, relationships
        with engine.connect() as conn:
            tbl_rows = conn.execute(
                text("SELECT * FROM insightforge.dataset_tables WHERE dataset_id = :id ORDER BY safe_name;"),
                {"id": ds_row.id}
            ).fetchall()

            rel_rows = conn.execute(
                text("SELECT * FROM insightforge.dataset_relationships WHERE dataset_id = :id;"),
                {"id": ds_row.id}
            ).fetchall()

            tables: List[TableProfile] = []
            for t in tbl_rows:
                col_rows = conn.execute(
                    text("SELECT * FROM insightforge.dataset_columns WHERE table_id = :t_id ORDER BY safe_name;"),
                    {"t_id": t.id}
                ).fetchall()

                columns = [
                    ColumnProfile(
                        id=str(c.id),
                        original_name=c.original_name,
                        safe_name=c.safe_name,
                        pg_type=c.pg_type,
                        role=c.role,
                        null_pct=float(c.null_pct),
                        distinct_count=int(c.distinct_count),
                        min_val=c.min_val,
                        max_val=c.max_val,
                        stats=c.stats if isinstance(c.stats, dict) else json.loads(c.stats or "{}"),
                        user_description=c.user_description
                    ) for c in col_rows
                ]

                tables.append(TableProfile(
                    id=str(t.id),
                    original_name=t.original_name,
                    safe_name=t.safe_name,
                    row_count=int(t.row_count),
                    column_count=int(t.column_count),
                    candidate_pk=t.candidate_pk,
                    candidate_time_column=t.candidate_time_column,
                    quality_findings=t.quality_findings if isinstance(t.quality_findings, list) else json.loads(t.quality_findings or "[]"),
                    columns=columns
                ))

            relationships = [
                RelationshipProfile(
                    id=str(r.id),
                    parent_table=r.parent_table,
                    parent_column=r.parent_column,
                    child_table=r.child_table,
                    child_column=r.child_column,
                    cardinality=r.cardinality,
                    confidence=float(r.confidence),
                    confirmed=bool(r.confirmed)
                ) for r in rel_rows
            ]

        return DatasetProfile(
            id=str(ds_row.id),
            name=ds_row.name,
            schema_name=ds_row.schema_name,
            status=ds_row.status,
            share_samples=ds_row.share_samples,
            source_files=ds_row.source_files if isinstance(ds_row.source_files, list) else json.loads(ds_row.source_files or "[]"),
            size_bytes=int(ds_row.size_bytes),
            created_at=ds_row.created_at,
            expires_at=ds_row.expires_at,
            is_demo=is_demo,
            tables=tables,
            relationships=relationships
        )

    @classmethod
    def _get_olist_demo_profile(cls, ds_row: Any) -> DatasetProfile:
        """Returns metadata profile for the canonical Olist demo dataset."""
        # Built-in canonical tables and relationships
        tables = [
            TableProfile(
                original_name="orders.csv",
                safe_name="orders",
                row_count=99441,
                column_count=8,
                candidate_pk="order_id",
                candidate_time_column="order_purchase_timestamp",
                quality_findings=[{"type": "delivered_orders", "severity": "info", "message": "96,478 delivered orders"}],
                columns=[
                    ColumnProfile(original_name="order_id", safe_name="order_id", pg_type="VARCHAR(32)", role="id", distinct_count=99441),
                    ColumnProfile(original_name="customer_id", safe_name="customer_id", pg_type="VARCHAR(32)", role="id", distinct_count=99441),
                    ColumnProfile(original_name="order_status", safe_name="order_status", pg_type="VARCHAR(16)", role="dimension", distinct_count=8),
                    ColumnProfile(original_name="order_purchase_timestamp", safe_name="order_purchase_timestamp", pg_type="TIMESTAMP", role="datetime"),
                    ColumnProfile(original_name="order_delivered_customer_date", safe_name="order_delivered_customer_date", pg_type="TIMESTAMP", role="datetime"),
                    ColumnProfile(original_name="order_estimated_delivery_date", safe_name="order_estimated_delivery_date", pg_type="TIMESTAMP", role="datetime")
                ]
            ),
            TableProfile(
                original_name="order_items.csv",
                safe_name="order_items",
                row_count=112650,
                column_count=7,
                candidate_pk="order_item_id",
                candidate_time_column="shipping_limit_date",
                columns=[
                    ColumnProfile(original_name="order_id", safe_name="order_id", pg_type="VARCHAR(32)", role="id", distinct_count=98666),
                    ColumnProfile(original_name="order_item_id", safe_name="order_item_id", pg_type="INTEGER", role="id"),
                    ColumnProfile(original_name="product_id", safe_name="product_id", pg_type="VARCHAR(32)", role="id", distinct_count=32951),
                    ColumnProfile(original_name="seller_id", safe_name="seller_id", pg_type="VARCHAR(32)", role="id", distinct_count=3095),
                    ColumnProfile(original_name="price", safe_name="price", pg_type="NUMERIC(10, 2)", role="measure", min_val="0.85", max_val="6735.00"),
                    ColumnProfile(original_name="freight_value", safe_name="freight_value", pg_type="NUMERIC(10, 2)", role="measure")
                ]
            ),
            TableProfile(
                original_name="customers.csv",
                safe_name="customers",
                row_count=99441,
                column_count=5,
                candidate_pk="customer_id",
                columns=[
                    ColumnProfile(original_name="customer_id", safe_name="customer_id", pg_type="VARCHAR(32)", role="id", distinct_count=99441),
                    ColumnProfile(original_name="customer_unique_id", safe_name="customer_unique_id", pg_type="VARCHAR(32)", role="id", distinct_count=96096),
                    ColumnProfile(original_name="customer_state", safe_name="customer_state", pg_type="VARCHAR(2)", role="dimension", distinct_count=27)
                ]
            )
        ]

        relationships = [
            RelationshipProfile(
                parent_table="orders",
                parent_column="order_id",
                child_table="order_items",
                child_column="order_id",
                cardinality="1:N",
                confidence=1.0,
                confirmed=True
            ),
            RelationshipProfile(
                parent_table="customers",
                parent_column="customer_id",
                child_table="orders",
                child_column="customer_id",
                cardinality="1:1",
                confidence=1.0,
                confirmed=True
            )
        ]

        return DatasetProfile(
            id=str(ds_row.id),
            name="Olist Brazilian E-Commerce",
            schema_name="insightforge",
            status="ready",
            share_samples=False,
            source_files=["customers.csv", "orders.csv", "order_items.csv", "products.csv", "sellers.csv", "order_payments.csv", "order_reviews.csv"],
            size_bytes=int(ds_row.size_bytes),
            created_at=ds_row.created_at,
            expires_at=None,
            is_demo=True,
            tables=tables,
            relationships=relationships
        )

    @classmethod
    def update_dataset(
        cls,
        dataset_id: str,
        owner_token: Optional[str] = None,
        req: Optional[Any] = None,
        share_samples: Optional[bool] = None,
        column_updates: Optional[List[Dict[str, Any]]] = None,
        confirmed_relationships: Optional[List[Dict[str, Any]]] = None
    ) -> DatasetProfile:
        """Updates dataset options (share_samples, column roles/descriptions, relationship confirmations)."""
        cls._assert_live_db()
        owner_hash = hash_token(owner_token) if owner_token else ""

        if req is not None:
            if share_samples is None:
                share_samples = req.share_samples
            if column_updates is None:
                column_updates = req.column_updates
            if confirmed_relationships is None:
                confirmed_relationships = req.confirmed_relationships

        with engine.connect() as conn:
            ds_row = conn.execute(
                text("SELECT * FROM insightforge.datasets WHERE id = :id;"),
                {"id": dataset_id if len(dataset_id) == 36 else "00000000-0000-0000-0000-000000000000"}
            ).fetchone()

        if not ds_row:
            raise FileValidationError("Dataset not found.", status_code=404)
        if ds_row.schema_name == "insightforge":
            raise FileValidationError("The built-in demo dataset cannot be modified.", status_code=403)
        if ds_row.owner_token_hash != owner_hash:
            raise FileValidationError("Access denied. Invalid owner token.", status_code=403)

        with engine.begin() as conn:
            if share_samples is not None:
                conn.execute(
                    text("UPDATE insightforge.datasets SET share_samples = :val WHERE id = :id;"),
                    {"val": share_samples, "id": dataset_id}
                )

            if column_updates:
                for up in column_updates:
                    table_name = up.get("table_name")
                    col_name = up.get("column_name")
                    role = up.get("role")
                    desc = up.get("user_description")

                    if table_name and col_name:
                        format_override = up.get("format_override")
                        if format_override:
                            conn.execute(
                                text("""
                                    UPDATE insightforge.dataset_columns c
                                    SET stats = COALESCE(c.stats, '{}'::jsonb) || jsonb_build_object('format_override', :fmt_val::text)
                                    FROM insightforge.dataset_tables t
                                    WHERE c.table_id = t.id
                                      AND t.dataset_id = :d_id
                                      AND t.safe_name = :t_name
                                      AND c.safe_name = :c_name;
                                """),
                                {"fmt_val": format_override, "d_id": dataset_id, "t_name": table_name, "c_name": col_name}
                            )

                        conn.execute(
                            text("""
                                UPDATE insightforge.dataset_columns c
                                SET role = COALESCE(:role, c.role),
                                    user_description = COALESCE(:desc, c.user_description)
                                FROM insightforge.dataset_tables t
                                WHERE c.table_id = t.id
                                  AND t.dataset_id = :d_id
                                  AND t.safe_name = :t_name
                                  AND c.safe_name = :c_name;
                            """),
                            {"role": role, "desc": desc, "d_id": dataset_id, "t_name": table_name, "c_name": col_name}
                        )

                        if role == "datetime":
                            conn.execute(
                                text("""
                                    UPDATE insightforge.dataset_tables
                                    SET candidate_time_column = :c_name
                                    WHERE dataset_id = :d_id AND safe_name = :t_name;
                                """),
                                {"c_name": col_name, "d_id": dataset_id, "t_name": table_name}
                            )

            if confirmed_relationships:
                for rel in confirmed_relationships:
                    conn.execute(
                        text("""
                            UPDATE insightforge.dataset_relationships
                            SET confirmed = :conf
                            WHERE dataset_id = :d_id
                              AND parent_table = :pt
                              AND parent_column = :pc
                              AND child_table = :ct
                              AND child_column = :cc;
                        """),
                        {
                            "conf": rel.get("confirmed", True),
                            "d_id": dataset_id,
                            "pt": rel.get("parent_table"),
                            "pc": rel.get("parent_column"),
                            "ct": rel.get("child_table"),
                            "cc": rel.get("child_column")
                        }
                    )

        return cls.get_dataset_profile(dataset_id, owner_token=owner_token)

    @classmethod
    def preview_table(
        cls,
        dataset_id: str,
        table_name: str,
        limit: int = 50,
        owner_token: Optional[str] = None
    ) -> TablePreviewResponse:
        """Previews up to 50 rows from a dataset table using readonly_engine and quoted identifiers."""
        cls._assert_live_db()
        owner_hash = hash_token(owner_token) if owner_token else ""

        with engine.connect() as conn:
            ds_row = conn.execute(
                text("SELECT schema_name, owner_token_hash FROM insightforge.datasets WHERE id = :id OR schema_name = :s_id;"),
                {"id": dataset_id if len(dataset_id) == 36 else "00000000-0000-0000-0000-000000000000", "s_id": dataset_id}
            ).fetchone()

        if not ds_row:
            raise FileValidationError("Dataset not found.", status_code=404)

        is_demo = (ds_row.schema_name == "insightforge")
        if not is_demo and ds_row.owner_token_hash != owner_hash:
            raise FileValidationError("Access denied. Invalid owner token.", status_code=403)

        schema_name = ds_row.schema_name
        limit = max(1, min(limit, 50))  # Cap at 50

        # Validate table_name against the dataset's registered tables (prevents cross-dataset access).
        # The demo dataset (insightforge schema) skips this check; its tables are fixed by views.sql.
        if not is_demo:
            with engine.connect() as conn:
                allowed_rows = conn.execute(
                    text(
                        "SELECT safe_name FROM insightforge.dataset_tables "
                        "WHERE dataset_id = (SELECT id FROM insightforge.datasets WHERE schema_name = :s)"
                    ),
                    {"s": schema_name}
                ).fetchall()
            allowed_names = {r[0] for r in allowed_rows}
            if table_name not in allowed_names:
                raise FileValidationError(
                    f"Table '{table_name}' not found in this dataset.",
                    status_code=404
                )

        # Execute preview query via readonly_engine with quoted identifiers
        raw_ro_conn = readonly_engine.raw_connection()
        try:
            with raw_ro_conn.cursor() as cur:
                # 1. Total row count
                count_query = sql.SQL("SELECT count(*) FROM {}.{};").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name)
                )
                cur.execute(count_query)
                total_rows = cur.fetchone()[0]

                # 2. Preview rows
                query = sql.SQL("SELECT * FROM {}.{} LIMIT %s;").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name)
                )
                cur.execute(query, (limit,))
                col_names = [desc[0] for desc in cur.description]
                rows = cur.fetchall()

                formatted_rows = []
                for r in rows:
                    row_dict = {}
                    for col_idx, val in enumerate(r):
                        # Convert date/timestamp/uuid to string for clean JSON serialization
                        if isinstance(val, (datetime, pd.Timestamp)):
                            row_dict[col_names[col_idx]] = val.isoformat()
                        elif isinstance(val, uuid.UUID):
                            row_dict[col_names[col_idx]] = str(val)
                        elif val is None:
                            row_dict[col_names[col_idx]] = None
                        else:
                            row_dict[col_names[col_idx]] = str(val)
                    formatted_rows.append(row_dict)

            return TablePreviewResponse(
                dataset_id=dataset_id,
                table_name=table_name,
                total_rows=total_rows,
                preview_rows_count=len(formatted_rows),
                columns=col_names,
                rows=formatted_rows
            )
        finally:
            raw_ro_conn.close()

    @classmethod
    def delete_dataset(cls, dataset_id: str, owner_token: Optional[str] = None) -> bool:
        """Deletes a dataset, cascading metadata removal and dropping its PostgreSQL schema."""
        cls._assert_live_db()
        owner_hash = hash_token(owner_token) if owner_token else ""

        with engine.connect() as conn:
            ds_row = conn.execute(
                text("SELECT schema_name, owner_token_hash FROM insightforge.datasets WHERE id = :id;"),
                {"id": dataset_id if len(dataset_id) == 36 else "00000000-0000-0000-0000-000000000000"}
            ).fetchone()

        if not ds_row:
            raise FileValidationError("Dataset not found.", status_code=404)
        if ds_row.schema_name == "insightforge":
            raise FileValidationError("The built-in demo dataset cannot be deleted.", status_code=403)
        if ds_row.owner_token_hash != owner_hash:
            raise FileValidationError("Access denied. Invalid owner token.", status_code=403)

        schema_name = ds_row.schema_name

        # 1. Drop schema CASCADE with admin raw connection and drop defense-in-depth role
        raw_conn = engine.raw_connection()
        try:
            with raw_conn.cursor() as cur:
                cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE;").format(sql.Identifier(schema_name)))
                cur.execute("DELETE FROM insightforge.datasets WHERE id = %s;", (dataset_id,))

                # Drop defense-in-depth role
                if schema_name.startswith("ds_"):
                    role_name = f"dsr_{schema_name[3:]}"
                    try:
                        cur.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM {};").format(sql.Identifier(schema_name), sql.Identifier(role_name)))
                    except Exception:
                        pass
                    try:
                        cur.execute(sql.SQL("REVOKE {} FROM insightforge_ro;").format(sql.Identifier(role_name)))
                    except Exception:
                        pass
                    try:
                        cur.execute(sql.SQL("DROP ROLE IF EXISTS {};").format(sql.Identifier(role_name)))
                    except Exception as e:
                        logger.debug(f"Could not drop role {role_name}: {e}")
            raw_conn.commit()
        finally:
            raw_conn.close()

        # Audit log delete
        try:
            AIAuditService.log_interaction(
                question=f"[dataset_delete: id: {dataset_id}, schema: {schema_name}]",
                intent="dataset_delete",
                latency_ms=50.0,
                success=True
            )
        except Exception:
            pass

        return True
