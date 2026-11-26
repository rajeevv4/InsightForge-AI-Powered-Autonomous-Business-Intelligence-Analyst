import logging
import time
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from sqlalchemy import text

from backend.app.config import settings
from backend.app.database import readonly_engine
from backend.app.exceptions import DatabaseUnavailableError
from backend.app.fixture_guard import is_fixture_mode
from backend.app.schemas.dataset import DatasetProfile
from backend.app.schemas.dataset_semantic import (
    DatasetInsightsResponse,
    DatasetSemanticResponse,
    InsightChartSpec,
)
from backend.app.services.anomaly_service import AnomalyService
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_semantic_service import DatasetSemanticService
from backend.app.services.dataset_service import DatasetService
from backend.app.services.sql_validator import DatasetSQLContext, SQLValidator

logger = logging.getLogger(__name__)

# In-memory cache for insights: (dataset_id, "insights") -> (timestamp, DatasetInsightsResponse)
_INSIGHTS_CACHE: Dict[Tuple[str, str], Tuple[float, DatasetInsightsResponse]] = {}
INSIGHTS_CACHE_TTL = 300  # 5 minutes

_REVENUE_LIKE_KEYWORDS = ["amount", "revenue", "sales", "total", "price"]


def select_main_measure(numeric_measures: List[Any]) -> Any:
    """
    Measure used for the Trend over Time / Top Rankings charts.
    Prefers the first revenue/amount-like SUM measure; otherwise keeps the previous
    behaviour (first numeric measure). Caller guarantees the list is non-empty.
    """
    for m in numeric_measures:
        name = (m.column or "").lower()
        if (m.aggregation or "").upper() == "SUM" and any(k in name for k in _REVENUE_LIKE_KEYWORDS):
            return m
    return numeric_measures[0]


class DatasetInsightsService:
    """
    Computes deterministic quick insights (time trend, top-N, distribution)
    and generic MAD anomaly detection for dataset workspace.
    """

    @classmethod
    def clear_cache(cls, dataset_id: Optional[str] = None):
        """Clears insights cache for a dataset or all."""
        global _INSIGHTS_CACHE
        if dataset_id:
            key = (dataset_id, "insights")
            _INSIGHTS_CACHE.pop(key, None)
        else:
            _INSIGHTS_CACHE.clear()

    @classmethod
    def execute_guarded_sql_in_schema(
        cls,
        sanitized_sql: str,
        schema_name: str
    ) -> List[Dict[str, Any]]:
        """Executes guarded SQL via readonly_engine with SET LOCAL search_path."""
        if is_fixture_mode():
            return []
        try:
            with readonly_engine.connect() as conn:
                with conn.begin():
                    if schema_name.startswith("ds_"):
                        role_name = f"dsr_{schema_name[3:]}"
                        try:
                            conn.execute(text(f'SET LOCAL ROLE "{role_name}";'))
                        except Exception as e:
                            logger.debug(f"Could not SET LOCAL ROLE {role_name}: {e}")
                    conn.execute(text(f'SET LOCAL search_path = "{schema_name}", public;'))
                    result = conn.execute(text(sanitized_sql))
                    cols = list(result.keys())
                    rows = [dict(zip(cols, row)) for row in result.fetchmany(500)]
                # Convert timestamps / decimals to serializable types
                clean_rows = []
                for r in rows:
                    clean_r = {}
                    for k, v in r.items():
                        if hasattr(v, "isoformat"):
                            clean_r[k] = v.isoformat()
                        elif isinstance(v, float) or isinstance(v, int) or v is None:
                            clean_r[k] = v
                        else:
                            try:
                                clean_r[k] = float(v)
                            except (ValueError, TypeError):
                                clean_r[k] = str(v)
                    clean_rows.append(clean_r)
                return clean_rows
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Insight query execution failed in schema '{schema_name}': {err_msg}")
            if any(k in err_msg.lower() for k in ["could not connect", "connection refused", "password authentication failed"]):
                raise DatabaseUnavailableError(f"Database unavailable: {err_msg}")
            raise

    @classmethod
    def get_insights(
        cls,
        dataset_id: str,
        owner_token: Optional[str] = None
    ) -> DatasetInsightsResponse:
        """
        Runs 3 template queries through SQLValidator and executes them.
        Generates generic anomalies if time series >= 30 points.
        Cache key includes dataset_id.
        """
        cache_key = (dataset_id, "insights")
        now = time.time()
        if cache_key in _INSIGHTS_CACHE:
            cached_time, cached_resp = _INSIGHTS_CACHE[cache_key]
            if now - cached_time < INSIGHTS_CACHE_TTL:
                return cached_resp

        # Enforce owner isolation and retrieve profile
        profile: DatasetProfile = DatasetService.get_dataset_profile(dataset_id, owner_token=owner_token)
        semantic_resp: DatasetSemanticResponse = DatasetSemanticService.get_semantic(dataset_id, owner_token=owner_token)
        model = semantic_resp.semantic_model

        schema_name = profile.schema_name
        is_demo = (schema_name == "insightforge")

        sql_context = DatasetSQLContext(
            schema_name=schema_name,
            allowed_tables={t.safe_name for t in profile.tables},
            relationships=[r.model_dump() for r in profile.relationships],
            table_columns={t.safe_name: {c.safe_name for c in t.columns} for t in profile.tables},
            is_demo=is_demo
        )

        if not profile.tables:
            return DatasetInsightsResponse(dataset_id=dataset_id)

        # 1. Select primary measure (numeric column)
        numeric_measures = [m for m in model.measures if m.column is not None]
        if numeric_measures:
            main_measure = select_main_measure(numeric_measures)
            t_name = main_measure.table
        else:
            main_measure = None
            t_name = profile.tables[0].safe_name

        # Select dimension from the same table if available, else first dimension
        same_table_dims = [d for d in model.dimensions if d.table == t_name]
        main_dim = same_table_dims[0] if same_table_dims else (model.dimensions[0] if model.dimensions else None)
        second_dim = same_table_dims[1] if len(same_table_dims) > 1 else (model.dimensions[1] if len(model.dimensions) > 1 else None)

        # Select time column from the same table if available
        same_table_times = [tc for tc in model.time_columns if tc.table == t_name]
        main_time_col = same_table_times[0] if same_table_times else (model.time_columns[0] if model.time_columns else None)

        # 1. Query 1: Time Trend
        time_trend_spec: Optional[InsightChartSpec] = None
        if main_time_col and main_measure and main_measure.column:
            t_col_name = main_time_col.column
            m_col_name = main_measure.column
            agg_fn = main_measure.aggregation.upper()
            is_date_type = any(k in main_time_col.data_type.upper() for k in ["TIMESTAMP", "DATE", "TIME"])
            t_expr = (
                f"DATE_TRUNC('month', {t_col_name})::date::text"
                if is_date_type else
                f"DATE_TRUNC('month', NULLIF({t_col_name}, '')::timestamp)::date::text"
            )

            if is_demo:
                raw_sql = (
                    f"SELECT {t_expr} AS period, "
                    f"{agg_fn}({m_col_name}) AS value "
                    f"FROM {t_name} WHERE {t_col_name} IS NOT NULL "
                    f"GROUP BY 1 ORDER BY 1 LIMIT 100;"
                )
            else:
                raw_sql = (
                    f"SELECT {t_expr} AS period, "
                    f"{agg_fn}({m_col_name}) AS value "
                    f"FROM {schema_name}.{t_name} WHERE {t_col_name} IS NOT NULL "
                    f"GROUP BY 1 ORDER BY 1 LIMIT 100;"
                )
            is_valid, sanitized_sql, err = SQLValidator.validate(raw_sql, context=sql_context)
            if is_valid and sanitized_sql:
                try:
                    rows = cls.execute_guarded_sql_in_schema(sanitized_sql, schema_name)
                    time_trend_spec = InsightChartSpec(
                        title=f"{main_measure.name} Trend over Time",
                        chart_type="line",
                        sql=sanitized_sql,
                        x_axis="period",
                        y_axis="value",
                        data=rows
                    )
                except Exception as e:
                    logger.warning(f"Time trend query failed on {t_name}: {e}")

        # Fallback time trend to dimension ranking if no time trend produced
        if not time_trend_spec and main_dim and main_measure and main_measure.column:
            d_col = main_dim.column
            m_col = main_measure.column
            agg_fn = main_measure.aggregation.upper()
            from_clause = f"{t_name}" if is_demo else f"{schema_name}.{t_name}"
            raw_sql = (
                f"SELECT {d_col}::text AS period, {agg_fn}({m_col}) AS value "
                f"FROM {from_clause} WHERE {d_col} IS NOT NULL "
                f"GROUP BY 1 ORDER BY 2 DESC LIMIT 15;"
            )
            is_valid, sanitized_sql, err = SQLValidator.validate(raw_sql, context=sql_context)
            if is_valid and sanitized_sql:
                try:
                    rows = cls.execute_guarded_sql_in_schema(sanitized_sql, schema_name)
                    time_trend_spec = InsightChartSpec(
                        title=f"{main_measure.name} by {main_dim.name}",
                        chart_type="line",
                        sql=sanitized_sql,
                        x_axis="period",
                        y_axis="value",
                        data=rows
                    )
                except Exception as e:
                    logger.warning(f"Fallback trend query failed: {e}")

        # 2. Query 2: Top-N Chart
        top_n_spec: Optional[InsightChartSpec] = None
        if main_dim and main_measure and main_measure.column:
            d_col = main_dim.column
            m_col = main_measure.column
            agg_fn = main_measure.aggregation.upper()
            if main_dim.table == t_name:
                from_clause = f"{t_name}" if is_demo else f"{schema_name}.{t_name}"
                raw_sql = (
                    f"SELECT {d_col}::text AS category, {agg_fn}({m_col}) AS value "
                    f"FROM {from_clause} WHERE {d_col} IS NOT NULL "
                    f"GROUP BY 1 ORDER BY 2 DESC LIMIT 10;"
                )
            else:
                rel = next((r for r in profile.relationships if (r.parent_table == main_dim.table and r.child_table == t_name) or (r.parent_table == t_name and r.child_table == main_dim.table)), None)
                if rel:
                    from_clause = f"{schema_name}.{rel.parent_table} p JOIN {schema_name}.{rel.child_table} c ON p.{rel.parent_column} = c.{rel.child_column}" if not is_demo else f"{rel.parent_table} p JOIN {rel.child_table} c ON p.{rel.parent_column} = c.{rel.child_column}"
                    col_dim = f"p.{d_col}" if rel.parent_table == main_dim.table else f"c.{d_col}"
                    col_meas = f"p.{m_col}" if rel.parent_table == t_name else f"c.{m_col}"
                    raw_sql = f"SELECT {col_dim}::text AS category, {agg_fn}({col_meas}) AS value FROM {from_clause} WHERE {col_dim} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 10;"
                else:
                    from_clause = f"{t_name}" if is_demo else f"{schema_name}.{t_name}"
                    raw_sql = (
                        f"SELECT {m_col}::text AS category, {agg_fn}({m_col}) AS value "
                        f"FROM {from_clause} WHERE {m_col} IS NOT NULL "
                        f"GROUP BY 1 ORDER BY 2 DESC LIMIT 10;"
                    )

            is_valid, sanitized_sql, err = SQLValidator.validate(raw_sql, context=sql_context)
            if is_valid and sanitized_sql:
                try:
                    rows = cls.execute_guarded_sql_in_schema(sanitized_sql, schema_name)
                    top_n_spec = InsightChartSpec(
                        title=f"Top 10 {main_dim.name} by {main_measure.name}",
                        chart_type="bar",
                        sql=sanitized_sql,
                        x_axis="category",
                        y_axis="value",
                        data=rows
                    )
                except Exception as e:
                    logger.warning(f"Top-N query failed: {e}")
        elif main_dim:
            # Count distribution
            d_col = main_dim.column
            from_clause = f"{main_dim.table}" if is_demo else f"{schema_name}.{main_dim.table}"
            raw_sql = (
                f"SELECT {d_col}::text AS category, COUNT(*) AS value "
                f"FROM {from_clause} WHERE {d_col} IS NOT NULL "
                f"GROUP BY 1 ORDER BY 2 DESC LIMIT 10;"
            )
            is_valid, sanitized_sql, err = SQLValidator.validate(raw_sql, context=sql_context)
            if is_valid and sanitized_sql:
                try:
                    rows = cls.execute_guarded_sql_in_schema(sanitized_sql, schema_name)
                    top_n_spec = InsightChartSpec(
                        title=f"Top 10 {main_dim.name} by Record Count",
                        chart_type="bar",
                        sql=sanitized_sql,
                        x_axis="category",
                        y_axis="value",
                        data=rows
                    )
                except Exception as e:
                    logger.warning(f"Top-N count query failed: {e}")

        # 3. Query 3: Distribution Chart
        distribution_spec: Optional[InsightChartSpec] = None
        target_dist_dim = second_dim or main_dim
        if target_dist_dim:
            dist_col = target_dist_dim.column
            from_clause = f"{target_dist_dim.table}" if is_demo else f"{schema_name}.{target_dist_dim.table}"
            raw_sql = (
                f"SELECT {dist_col}::text AS segment, COUNT(*) AS count "
                f"FROM {from_clause} WHERE {dist_col} IS NOT NULL "
                f"GROUP BY 1 ORDER BY 2 DESC LIMIT 10;"
            )
            is_valid, sanitized_sql, err = SQLValidator.validate(raw_sql, context=sql_context)
            if is_valid and sanitized_sql:
                try:
                    rows = cls.execute_guarded_sql_in_schema(sanitized_sql, schema_name)
                    distribution_spec = InsightChartSpec(
                        title=f"Record Distribution by {target_dist_dim.name}",
                        chart_type="pie",
                        sql=sanitized_sql,
                        x_axis="segment",
                        y_axis="count",
                        data=rows
                    )
                except Exception as e:
                    logger.warning(f"Distribution query failed: {e}")

        # 4. Anomaly detection on the primary measure's daily series.
        # Uses the shared dataset detector (rolling MAD + STL + IsolationForest, Olist calibration).
        # The previous inline version read AnomalyItem fields that do not exist, so it was always empty.
        anomalies_list: List[Dict[str, Any]] = []
        try:
            from backend.app.services.dataset_anomaly_service import DatasetAnomalyService  # lazy: avoids import cycle
            anomalies_list = DatasetAnomalyService.quick_insights_items(dataset_id, owner_token)
        except Exception as e:
            logger.warning(f"Generic anomaly detection failed for dataset '{dataset_id}': {e}")

        response = DatasetInsightsResponse(
            dataset_id=dataset_id,
            time_trend=time_trend_spec,
            top_n=top_n_spec,
            distribution=distribution_spec,
            anomalies=anomalies_list
        )

        _INSIGHTS_CACHE[cache_key] = (now, response)
        return response
