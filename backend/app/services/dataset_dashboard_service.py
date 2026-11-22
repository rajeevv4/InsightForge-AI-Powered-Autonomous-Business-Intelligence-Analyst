"""
Dataset Dashboard Service (uploaded datasets only)
==================================================
Builds a deterministic dashboard (KPIs, monthly trend, breakdowns, data quality,
anomalies) for an uploaded dataset. No LLM calls.

Safety model (reuses the existing dataset query path, adds nothing new):
- Owner check: DatasetService.get_dataset_profile (wrong/missing token -> 403).
- Every query: identifiers quoted with sqlglot (same library the validator parses with),
  validated by SQLValidator with a DatasetSQLContext, then executed by
  DatasetInsightsService.execute_guarded_sql_in_schema (read-only engine,
  statement_timeout, SET LOCAL ROLE dsr_<id>, SET LOCAL search_path).
- Semantic-model measures are re-checked against the real profile (table/column exist,
  numeric type, aggregation allow-list) because users can edit the semantic model.
- Joins: only fact -> dimension along a CONFIRMED relationship where the fact table is
  the child and the dimension-side key is unique per the profile (N:1). LEFT JOIN, so
  each fact row is counted exactly once (no fan-out). Anything else is skipped.
- Each section is isolated: a failure sets that section to None with a short reason.
- Cell values are only returned to the owner in this response; nothing is logged or
  sent to any LLM (share_samples is irrelevant here because no LLM is involved).
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
from sqlglot import exp

from backend.app.schemas.dataset import ColumnProfile, DatasetProfile, RelationshipProfile, TableProfile
from backend.app.schemas.dataset_semantic import (
    DashboardAnomalies,
    DashboardBreakdown,
    DashboardBreakdownItem,
    DashboardKPI,
    DashboardQualityTable,
    DashboardSkippedBreakdown,
    DashboardTrend,
    DatasetDashboardResponse,
    DimensionDefinition,
    MeasureDefinition,
    SemanticModel,
)
from backend.app.services.anomaly_service import AnomalyService
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_insights_service import DatasetInsightsService, select_main_measure
from backend.app.services.dataset_semantic_service import DatasetSemanticService
from backend.app.services.dataset_service import DatasetService
from backend.app.services.sql_validator import DatasetSQLContext, SQLValidator

logger = logging.getLogger(__name__)

ALLOWED_AGGREGATIONS = {"SUM", "AVG", "COUNT", "MIN", "MAX"}
NUMERIC_TYPE_MARKERS = ("INT", "NUMERIC", "FLOAT", "DOUBLE", "REAL", "DECIMAL")
TIME_TYPE_MARKERS = ("TIMESTAMP", "DATE", "TIME")

DASHBOARD_MAX_WORKERS = 4  # well under the read-only engine's pool (5 + 10 overflow)
MAX_BREAKDOWNS = 3
BREAKDOWN_TOP_N = 10
MAX_DIMENSION_DISTINCT = 100
MAX_DIMENSION_NULL_PCT = 50.0
# Business-friendly grouping columns are tried first (deterministic order).
DIMENSION_NAME_PRIORITY = [
    "category", "city", "state", "region", "country", "segment", "type",
    "method", "channel", "status", "brand", "station", "department", "gender",
]


def quote_ident(name: str) -> str:
    """Postgres-quoted identifier via sqlglot (embedded quotes are doubled)."""
    return exp.to_identifier(name, quoted=True).sql(dialect="postgres")


GRAIN_TRUNC = {"day": "day", "week": "week", "month": "month"}
GRAIN_LABEL = {"day": "Day", "week": "Week", "month": "Month"}


def measure_expr(m: MeasureDefinition, alias: Optional[str] = None) -> str:
    """AGG("col") / AGG("alias"."col"), or COUNT(*) for row-count measures."""
    if m.column is None:
        return "COUNT(*)"
    col = quote_ident(m.column) if alias is None else f"{quote_ident(alias)}.{quote_ident(m.column)}"
    return f"{m.aggregation.upper()}({col})"


def _short(err: Exception, limit: int = 160) -> str:
    """Short, value-free error reason for section_errors."""
    msg = str(err).splitlines()[0] if str(err) else type(err).__name__
    return msg[:limit]


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class DatasetDashboardService:
    """Deterministic dashboard for uploaded datasets."""

    # ------------------------------------------------------------------ helpers
    @classmethod
    def _run(cls, raw_sql: str, ctx: DatasetSQLContext, schema_name: str) -> List[Dict[str, Any]]:
        """Validate with the dataset-scoped AST validator, then run on the existing read-only path."""
        is_valid, sanitized_sql, err = SQLValidator.validate(raw_sql, context=ctx)
        if not is_valid or not sanitized_sql:
            raise ValueError(f"Query rejected by SQL validator: {err}")
        return DatasetInsightsService.execute_guarded_sql_in_schema(sanitized_sql, schema_name)

    @staticmethod
    def _column(profile: DatasetProfile, table: str, column: Optional[str]) -> Tuple[Optional[TableProfile], Optional[ColumnProfile]]:
        tbl = next((t for t in profile.tables if t.safe_name == table), None)
        if not tbl or column is None:
            return tbl, None
        return tbl, next((c for c in tbl.columns if c.safe_name == column), None)

    @classmethod
    def valid_measures(cls, profile: DatasetProfile, model: SemanticModel) -> Tuple[List[MeasureDefinition], List[str]]:
        """Measures safe to aggregate: known table/column, numeric column, allow-listed aggregation."""
        ok: List[MeasureDefinition] = []
        rejected: List[str] = []
        for m in model.measures:
            agg = (m.aggregation or "").upper()
            tbl, col = cls._column(profile, m.table, m.column)
            if agg not in ALLOWED_AGGREGATIONS or tbl is None:
                rejected.append(m.safe_name)
                continue
            if m.column is None:
                if agg == "COUNT":
                    ok.append(m)
                else:
                    rejected.append(m.safe_name)
                continue
            if col is None or not any(k in col.pg_type.upper() for k in NUMERIC_TYPE_MARKERS):
                rejected.append(m.safe_name)
                continue
            ok.append(m)
        return ok, rejected

    @staticmethod
    def find_safe_join(
        profile: DatasetProfile, fact_table: str, dim_table: str
    ) -> Tuple[Optional[RelationshipProfile], Optional[str]]:
        """
        Returns (relationship, None) for a safe N:1 path fact -> dim, else (None, reason).
        Safe = confirmed, fact is the child (many) side, and the dim-side key is unique
        (distinct_count == row_count, no nulls) according to the profile.
        """
        rels = [
            r for r in profile.relationships
            if {r.parent_table, r.child_table} == {fact_table, dim_table}
        ]
        if not rels:
            return None, f"no relationship between {fact_table} and {dim_table}"
        n1 = [r for r in rels if r.child_table == fact_table and r.parent_table == dim_table]
        if not n1:
            return None, f"{fact_table} -> {dim_table} is 1:N and would multiply rows"
        confirmed = [r for r in n1 if r.confirmed]
        if not confirmed:
            return None, (f"relationship {fact_table}.{n1[0].child_column} -> {dim_table}.{n1[0].parent_column} "
                          f"is not confirmed (confirm it on the Datasets page)")
        for r in confirmed:
            dim_tbl = next((t for t in profile.tables if t.safe_name == dim_table), None)
            key = next((c for c in dim_tbl.columns if c.safe_name == r.parent_column), None) if dim_tbl else None
            if key is not None and dim_tbl.row_count > 0 and key.distinct_count == dim_tbl.row_count and float(key.null_pct or 0) == 0.0:
                return r, None
        return None, f"key {dim_table}.{confirmed[0].parent_column} is not unique, join could multiply rows"

    @classmethod
    def _time_column(cls, profile: DatasetProfile, model: SemanticModel, table: str):
        """First semantic time column on `table` that exists in the profile -> (TimeColumnDefinition, ColumnProfile)."""
        for cand in model.time_columns:
            if cand.table != table:
                continue
            _, col = cls._column(profile, cand.table, cand.column)
            if col is not None:
                return cand, col
        return None

    @staticmethod
    def eligible_dimension(profile: DatasetProfile, d: DimensionDefinition) -> Optional[str]:
        """None if the dimension is a sensible grouping column, else a reason."""
        tbl = next((t for t in profile.tables if t.safe_name == d.table), None)
        col = next((c for c in tbl.columns if c.safe_name == d.column), None) if tbl else None
        if tbl is None or col is None:
            return "unknown column"
        if col.role == "id" or col.safe_name == tbl.candidate_pk:
            return "identifier column"
        if any(k in col.pg_type.upper() for k in NUMERIC_TYPE_MARKERS):
            return "numeric column (shown as a KPI instead)"
        if col.distinct_count < 2:
            return "constant column"
        if col.distinct_count >= tbl.row_count or col.distinct_count > MAX_DIMENSION_DISTINCT:
            return "too many distinct values"
        if float(col.null_pct or 0) > MAX_DIMENSION_NULL_PCT:
            return "mostly empty"
        return None

    @staticmethod
    def _dimension_rank(d: DimensionDefinition, fact_table: str) -> Tuple[int, int, str, str]:
        name = d.column.lower()
        prio = next((i for i, k in enumerate(DIMENSION_NAME_PRIORITY) if k in name), len(DIMENSION_NAME_PRIORITY))
        return (prio, 0 if d.table == fact_table else 1, d.table, d.column)

    # ------------------------------------------------------------------ sections
    @classmethod
    def build_kpis_for_table(cls, profile: DatasetProfile, tbl: TableProfile, measures: List[MeasureDefinition],
                             ctx: DatasetSQLContext) -> List[DashboardKPI]:
        """One query for this table: COUNT(*) plus every valid measure on it. Never raises."""
        t_measures = [m for m in measures if m.table == tbl.safe_name]
        if not any(m.column is None for m in t_measures):
            t_measures.insert(0, MeasureDefinition(name=f"{tbl.safe_name} rows", safe_name=f"{tbl.safe_name}_count",
                                                   table=tbl.safe_name, column=None, aggregation="COUNT"))
        select_parts = []
        for i, m in enumerate(t_measures):
            agg = m.aggregation.upper()
            expr = "COUNT(*)" if m.column is None else f"{agg}({quote_ident(m.column)})"
            select_parts.append(f"{expr} AS {quote_ident(f'k{i}')}")
        raw_sql = f"SELECT {', '.join(select_parts)} FROM {quote_ident(profile.schema_name)}.{quote_ident(tbl.safe_name)}"
        try:
            rows = cls._run(raw_sql, ctx, profile.schema_name)
            row = rows[0] if rows else {}
            err = None if rows else "no result"
        except Exception as e:
            logger.warning(f"Dashboard KPI query failed for table '{tbl.safe_name}': {_short(e)}")
            row, err = {}, _short(e)
        return [DashboardKPI(
            label=m.name if m.column is not None else f"{tbl.safe_name.replace('_', ' ').title()} Rows",
            table=tbl.safe_name, column=m.column, aggregation=m.aggregation.upper(),
            value=_num(row.get(f"k{i}")), error=err,
        ) for i, m in enumerate(t_measures)]

    @classmethod
    def build_kpis(cls, profile: DatasetProfile, measures: List[MeasureDefinition],
                   ctx: DatasetSQLContext) -> List[DashboardKPI]:
        return [k for t in profile.tables for k in cls.build_kpis_for_table(profile, t, measures, ctx)]

    @classmethod
    def build_trend(cls, profile: DatasetProfile, model: SemanticModel, primary: MeasureDefinition,
                    ctx: DatasetSQLContext, grain: str = "month") -> Tuple[Optional[DashboardTrend], Optional[str]]:
        grain = grain if grain in GRAIN_TRUNC else "month"
        tc = cls._time_column(profile, model, primary.table)
        if tc is None:
            return None, f"no date/time column in table '{primary.table}'"
        cand, col = tc
        t = quote_ident(cand.column)
        is_time_type = any(k in col.pg_type.upper() for k in TIME_TYPE_MARKERS)
        t_value = t if is_time_type else f"NULLIF({t}, '')::timestamp"
        agg = primary.aggregation.upper()
        raw_sql = (
            f"SELECT CAST(DATE_TRUNC('{GRAIN_TRUNC[grain]}', {t_value}) AS DATE)::text AS period, "
            f"{measure_expr(primary)} AS value "
            f"FROM {quote_ident(profile.schema_name)}.{quote_ident(primary.table)} "
            f"WHERE {t} IS NOT NULL GROUP BY 1 ORDER BY 1"
        )
        rows = cls._run(raw_sql, ctx, profile.schema_name)
        return DashboardTrend(
            # The validator caps results at 500 rows; say so instead of silently truncating.
            title=f"{primary.name} by {GRAIN_LABEL[grain]}" + (" (first 500 periods)" if len(rows) >= 500 else ""),
            table=primary.table, measure_column=primary.column or "*", measure_label=primary.name,
            aggregation=agg, time_column=cand.column,
            points=[{"period": r.get("period"), "value": _num(r.get("value"))} for r in rows],
        ), None

    @classmethod
    def plan_breakdowns(cls, profile: DatasetProfile, model: SemanticModel, primary: MeasureDefinition,
                        max_breakdowns: int = MAX_BREAKDOWNS,
                        dimension_filter: Optional[Callable[[DimensionDefinition], bool]] = None,
                        ) -> Tuple[List[Tuple[DimensionDefinition, Optional[RelationshipProfile]]], List[DashboardSkippedBreakdown]]:
        """Pick up to MAX_BREAKDOWNS dimensions with a safe path; report the rest as skipped."""
        planned: List[Tuple[DimensionDefinition, Optional[RelationshipProfile]]] = []
        skipped: List[DashboardSkippedBreakdown] = []
        candidates = []
        for d in model.dimensions:
            if d.column is None:
                continue
            if dimension_filter is not None and not dimension_filter(d):
                continue
            if cls.eligible_dimension(profile, d) is None:
                candidates.append(d)
        for d in sorted(candidates, key=lambda x: cls._dimension_rank(x, primary.table)):
            if len(planned) >= max_breakdowns:
                break
            if d.table == primary.table:
                planned.append((d, None))
                continue
            rel, reason = cls.find_safe_join(profile, primary.table, d.table)
            if rel is None:
                skipped.append(DashboardSkippedBreakdown(dimension=f"{d.table}.{d.column}", reason=reason or "no safe join"))
            else:
                planned.append((d, rel))
        return planned, skipped

    @classmethod
    def build_breakdown(cls, profile: DatasetProfile, primary: MeasureDefinition, d: DimensionDefinition,
                        rel: Optional[RelationshipProfile], ctx: DatasetSQLContext,
                        top_n: int = BREAKDOWN_TOP_N) -> DashboardBreakdown:
        S = quote_ident(profile.schema_name)
        F, D = quote_ident("f"), quote_ident("d")
        agg = primary.aggregation.upper()
        m_expr = measure_expr(primary, alias="f")
        if rel is None:
            dim_expr = f"{F}.{quote_ident(d.column)}"
            from_sql = f"{S}.{quote_ident(primary.table)} AS {F}"
            join_path = None
        else:
            dim_expr = f"{D}.{quote_ident(d.column)}"
            from_sql = (
                f"{S}.{quote_ident(primary.table)} AS {F} LEFT JOIN {S}.{quote_ident(d.table)} AS {D} "
                f"ON {F}.{quote_ident(rel.child_column)} = {D}.{quote_ident(rel.parent_column)}"
            )
            join_path = f"{primary.table}.{rel.child_column} -> {d.table}.{rel.parent_column} (N:1)"
        raw_sql = (
            f"SELECT CAST({dim_expr} AS TEXT) AS label, {m_expr} AS value, COUNT(*) AS n "
            f"FROM {from_sql} GROUP BY 1 ORDER BY 2 DESC NULLS LAST"
        )
        rows = cls._run(raw_sql, ctx, profile.schema_name)
        groups = [(r.get("label") if r.get("label") is not None else "(blank)", _num(r.get("value")), int(r.get("n") or 0)) for r in rows]
        top, rest = groups[:top_n], groups[top_n:]
        is_sum = agg in ("SUM", "COUNT")
        return DashboardBreakdown(
            title=f"{primary.name} by {d.name}",
            dimension_table=d.table, dimension_column=d.column, dimension_label=d.name,
            measure_label=primary.name, aggregation=agg, join_path=join_path,
            items=[DashboardBreakdownItem(label=str(lbl), value=val, row_count=n) for lbl, val, n in top],
            other_value=(sum(v or 0.0 for _, v, _ in rest) if (is_sum and rest) else None),
            other_groups=len(rest),
            total_value=(sum(v or 0.0 for _, v, _ in groups) if is_sum else None),
            truncated=len(rows) >= 500,
        )

    @staticmethod
    def build_data_quality(profile: DatasetProfile) -> List[DashboardQualityTable]:
        out = []
        for t in profile.tables:
            findings = []
            for f in t.quality_findings or []:
                if not isinstance(f, dict):
                    continue
                findings.append({
                    "type": f.get("type") or "warning",
                    "column": f.get("column"),
                    "severity": f.get("severity") or "low",
                    "message": f.get("message") or f.get("description") or f.get("warning") or "",
                })
            out.append(DashboardQualityTable(table=t.safe_name, row_count=t.row_count, findings=findings))
        return out

    @classmethod
    def build_anomalies(cls, profile: DatasetProfile, model: SemanticModel, primary: MeasureDefinition,
                        ctx: DatasetSQLContext) -> Tuple[Optional[DashboardAnomalies], Optional[str]]:
        """
        Same detector and parameters Quick Insights uses (AnomalyService.detect_rolling_zscore,
        window=14, threshold=2.5, >= 30 daily points) on the primary measure's daily series.
        Called directly rather than via get_insights(), whose result mapping currently fails
        (it reads AnomalyItem fields that do not exist), so its anomaly list is always empty.
        """
        tc = cls._time_column(profile, model, primary.table)
        if tc is None:
            return None, f"no date/time column in table '{primary.table}'"
        cand, col = tc
        t = quote_ident(cand.column)
        is_time_type = any(k in col.pg_type.upper() for k in TIME_TYPE_MARKERS)
        t_value = t if is_time_type else f"NULLIF({t}, '')::timestamp"
        day_expr = f"CAST(DATE_TRUNC('day', {t_value}) AS DATE)"
        raw_sql = (
            f"SELECT {day_expr}::text AS period, {day_expr} AS period_date, "
            f"{primary.aggregation.upper()}({quote_ident(primary.column)}) AS metric_val "
            f"FROM {quote_ident(profile.schema_name)}.{quote_ident(primary.table)} "
            f"WHERE {t} IS NOT NULL GROUP BY 1, 2 ORDER BY 1"
        )
        rows = cls._run(raw_sql, ctx, profile.schema_name)
        label = primary.name
        if len(rows) < 30:
            return DashboardAnomalies(measure_label=label, items=[],
                                      note=f"Needs at least 30 days of data for anomaly detection (found {len(rows)})."), None
        df = pd.DataFrame(rows)
        df["metric_val"] = pd.to_numeric(df["metric_val"], errors="coerce").fillna(0.0)
        detected = AnomalyService.detect_rolling_zscore(df=df, metric="metric_val", window=14, threshold=2.5)
        items = [{
            "period": a.period,
            "observed": a.observed,
            "expected": a.expected,
            "deviation_score": a.deviation_score,
            "severity": a.severity,
            "direction": a.direction,
        } for a in detected]
        note = None if items else f"No unusual days found across {len(rows)} days of data."
        return DashboardAnomalies(measure_label=label, items=items, note=note), None

    # ------------------------------------------------------------------ entrypoint
    @classmethod
    def get_dashboard(cls, dataset_id: str, owner_token: Optional[str] = None) -> DatasetDashboardResponse:
        # Owner isolation (403 on wrong/missing token, 404 on unknown id)
        profile: DatasetProfile = DatasetService.get_dataset_profile(dataset_id, owner_token=owner_token)
        if profile.is_demo or profile.schema_name == "insightforge":
            raise FileValidationError("The dashboard is only available for uploaded datasets. Use the Olist pages for the demo dataset.", status_code=400)

        resp = DatasetDashboardResponse(dataset_id=profile.id, dataset_name=profile.name)
        if not profile.tables:
            for s in ("kpis", "trend", "breakdowns", "data_quality", "anomalies"):
                resp.section_errors[s] = "dataset has no tables"
            return resp

        ctx = DatasetSQLContext(
            schema_name=profile.schema_name,
            allowed_tables={t.safe_name for t in profile.tables},
            relationships=[r.model_dump() for r in profile.relationships],
            table_columns={t.safe_name: {c.safe_name for c in t.columns} for t in profile.tables},
            is_demo=False,
        )

        # Data quality needs no queries; never depends on the semantic layer.
        try:
            resp.data_quality = cls.build_data_quality(profile)
        except Exception as e:
            resp.section_errors["data_quality"] = _short(e)

        try:
            model = DatasetSemanticService.get_semantic(dataset_id, owner_token=owner_token, allow_llm=False).semantic_model
        except Exception as e:
            reason = f"semantic model unavailable: {_short(e)}"
            for s in ("kpis", "trend", "breakdowns", "anomalies"):
                resp.section_errors[s] = reason
            return resp

        measures, _rejected = cls.valid_measures(profile, model)
        numeric = [m for m in measures if m.column is not None]
        primary = select_main_measure(numeric) if numeric else None
        if primary:
            resp.primary_measure = f"{primary.table}.{primary.column}"

        # Plan breakdowns up front (pure, no queries)
        planned: List[Tuple[DimensionDefinition, Optional[RelationshipProfile]]] = []
        if primary is not None:
            try:
                planned, resp.skipped_breakdowns = cls.plan_breakdowns(profile, model, primary)
            except Exception as e:
                resp.section_errors["breakdowns"] = _short(e)

        # Independent read-only queries run concurrently (each on its own pooled connection
        # via execute_guarded_sql_in_schema). Each task's failure only affects its own section.
        tasks: Dict[str, Callable[[], Any]] = {}
        for i, tbl in enumerate(profile.tables):
            tasks[f"kpi:{i}"] = (lambda t=tbl: cls.build_kpis_for_table(profile, t, measures, ctx))
        if primary is not None:
            tasks["trend"] = lambda: cls.build_trend(profile, model, primary, ctx)
            tasks["anomalies"] = lambda: cls.build_anomalies(profile, model, primary, ctx)
            for i, (d, rel) in enumerate(planned):
                tasks[f"breakdown:{i}"] = (lambda d=d, rel=rel: cls.build_breakdown(profile, primary, d, rel, ctx))

        results: Dict[str, Tuple[bool, Any]] = {}
        with ThreadPoolExecutor(max_workers=DASHBOARD_MAX_WORKERS) as pool:
            futures = {name: pool.submit(fn) for name, fn in tasks.items()}
            for name, fut in futures.items():
                try:
                    results[name] = (True, fut.result())
                except Exception as e:
                    logger.warning(f"Dashboard section task '{name}' failed: {_short(e)}")
                    results[name] = (False, _short(e))

        # KPIs (per-table tasks never raise; they carry their own error field)
        kpis: List[DashboardKPI] = []
        for i in range(len(profile.tables)):
            ok, val = results.get(f"kpi:{i}", (False, "not run"))
            if ok:
                kpis.extend(val)
        resp.kpis = kpis

        if primary is None:
            for s in ("trend", "breakdowns", "anomalies"):
                resp.section_errors[s] = "no numeric measure in this dataset"
            return resp

        for name in ("trend", "anomalies"):
            ok, val = results[name]
            if ok:
                section, reason = val
                setattr(resp, name, section)
                if reason:
                    resp.section_errors[name] = reason
            else:
                resp.section_errors[name] = val

        if "breakdowns" not in resp.section_errors:
            built: List[DashboardBreakdown] = []
            for i, (d, _rel) in enumerate(planned):
                ok, val = results[f"breakdown:{i}"]
                if ok:
                    built.append(val)
                else:
                    resp.skipped_breakdowns.append(DashboardSkippedBreakdown(dimension=f"{d.table}.{d.column}", reason=val))
            resp.breakdowns = built
            if not built:
                resp.section_errors["breakdowns"] = "no suitable grouping column with a safe join path"

        return resp
