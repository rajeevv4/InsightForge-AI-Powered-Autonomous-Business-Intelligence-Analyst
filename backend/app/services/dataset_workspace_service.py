"""
Dataset Workspace Service (uploaded datasets only)
==================================================
Backs the dataset-aware Overview / Analytics / Table / Group pages. Deterministic, no LLM.

Everything reuses DatasetDashboardService, so the safety model is identical:
- owner check via DatasetService.get_dataset_profile (wrong/missing token -> 403)
- semantic model loaded with allow_llm=False (never triggers Gemini enrichment)
- measures re-validated against the profile; sqlglot-quoted identifiers
- every query validated by SQLValidator(DatasetSQLContext) and executed by the existing
  read-only path (DatasetInsightsService.execute_guarded_sql_in_schema)
- joins only along confirmed N:1 relationships (find_safe_join); LEFT JOIN, no fan-out
- each section fails independently (null + reason in section_errors)

Caching: in-memory, keyed by (kind, dataset_id, params). Each entry remembers the hash of
the owner token that produced it; a different/missing token never gets a cached answer
(it takes the full path and gets 403). Entries expire after WORKSPACE_CACHE_TTL_SECONDS and
are invalidated by the router whenever relationships, the semantic model or the dataset change.
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.app.schemas.dataset import DatasetProfile
from backend.app.schemas.dataset_semantic import (
    DashboardBreakdown,
    DashboardKPI,
    DashboardSkippedBreakdown,
    MeasureDefinition,
    SemanticModel,
)
from backend.app.schemas.dataset_workspace import (
    MetricOption,
    WorkspaceAnalyticsResponse,
    WorkspaceOverviewResponse,
)
from backend.app.services.dataset_dashboard_service import DatasetDashboardService, _short
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_insights_service import select_main_measure
from backend.app.services.dataset_semantic_service import DatasetSemanticService
from backend.app.services.dataset_service import DatasetService, hash_token
from backend.app.services.sql_validator import DatasetSQLContext

logger = logging.getLogger(__name__)

WORKSPACE_CACHE_TTL_SECONDS = 600
WORKSPACE_MAX_WORKERS = 4
MAX_BREAKDOWN_LIMIT = 8
GRAIN_PARAM = {"daily": "day", "weekly": "week", "monthly": "month"}


# --------------------------------------------------------------------------- cache
class WorkspaceCache:
    _entries: Dict[Tuple, Tuple[str, float, Any]] = {}
    _lock = threading.Lock()

    @classmethod
    def get_or_compute(cls, kind: str, dataset_id: str, owner_token: Optional[str], params: Tuple,
                       compute: Callable[[], Any]) -> Any:
        key = (kind, dataset_id, params)
        owner_hash = hash_token(owner_token) if owner_token else ""
        now = time.time()
        with cls._lock:
            hit = cls._entries.get(key)
        if hit and owner_hash and hit[0] == owner_hash and now - hit[1] < WORKSPACE_CACHE_TTL_SECONDS:
            return hit[2].model_copy(update={"cached": True})
        value = compute()  # performs the owner check; raises 403/404 for a wrong token
        with cls._lock:
            cls._entries[key] = (owner_hash, time.time(), value)
        return value

    @classmethod
    def invalidate(cls, dataset_id: Optional[str] = None) -> None:
        with cls._lock:
            if dataset_id is None:
                cls._entries.clear()
            else:
                cls._entries = {k: v for k, v in cls._entries.items() if k[1] != dataset_id}


# --------------------------------------------------------------------------- context
@dataclass
class WorkspaceContext:
    profile: DatasetProfile
    ctx: DatasetSQLContext
    model: Optional[SemanticModel] = None
    model_error: Optional[str] = None
    measures: List[MeasureDefinition] = field(default_factory=list)
    primary: Optional[MeasureDefinition] = None


def load_context(dataset_id: str, owner_token: Optional[str]) -> WorkspaceContext:
    profile: DatasetProfile = DatasetService.get_dataset_profile(dataset_id, owner_token=owner_token)
    if profile.is_demo or profile.schema_name == "insightforge":
        raise FileValidationError("This page is computed only for uploaded datasets; the Olist demo uses its own pages.", status_code=400)
    ctx = DatasetSQLContext(
        schema_name=profile.schema_name,
        allowed_tables={t.safe_name for t in profile.tables},
        relationships=[r.model_dump() for r in profile.relationships],
        table_columns={t.safe_name: {c.safe_name for c in t.columns} for t in profile.tables},
        is_demo=False,
    )
    wc = WorkspaceContext(profile=profile, ctx=ctx)
    try:
        wc.model = DatasetSemanticService.get_semantic(dataset_id, owner_token=owner_token, allow_llm=False).semantic_model
    except FileValidationError:
        raise
    except Exception as e:
        wc.model_error = f"semantic model unavailable: {_short(e)}"
        return wc
    wc.measures, _ = DatasetDashboardService.valid_measures(profile, wc.model)
    numeric = [m for m in wc.measures if m.column is not None]
    wc.primary = select_main_measure(numeric) if numeric else next((m for m in wc.measures if m.column is None), None)
    return wc


def metric_key(m: MeasureDefinition) -> str:
    return f"{m.table}.{m.column if m.column is not None else '*'}"


def metric_options(measures: List[MeasureDefinition]) -> List[MetricOption]:
    out = []
    for m in measures:
        label = m.name if m.column is not None else f"{m.table.replace('_', ' ').title()} Rows"
        out.append(MetricOption(key=metric_key(m), label=label, table=m.table, column=m.column, aggregation=m.aggregation.upper()))
    return out


def run_tasks(tasks: Dict[str, Callable[[], Any]]) -> Dict[str, Tuple[bool, Any]]:
    """Run independent read-only query tasks concurrently; each failure is isolated."""
    results: Dict[str, Tuple[bool, Any]] = {}
    if not tasks:
        return results
    with ThreadPoolExecutor(max_workers=WORKSPACE_MAX_WORKERS) as pool:
        futures = {name: pool.submit(fn) for name, fn in tasks.items()}
        for name, fut in futures.items():
            try:
                results[name] = (True, fut.result())
            except Exception as e:
                logger.warning(f"Workspace task '{name}' failed: {_short(e)}")
                results[name] = (False, _short(e))
    return results


def clamp_limit(limit: Optional[int]) -> int:
    try:
        return max(1, min(MAX_BREAKDOWN_LIMIT, int(limit if limit is not None else MAX_BREAKDOWN_LIMIT)))
    except (TypeError, ValueError):
        return MAX_BREAKDOWN_LIMIT


def schedule_breakdowns(wc: WorkspaceContext, measure: MeasureDefinition, limit: int, tasks: Dict[str, Callable],
                        dimension_filter=None, prefix: str = "bd") -> Tuple[list, List[DashboardSkippedBreakdown]]:
    planned, skipped = DatasetDashboardService.plan_breakdowns(
        wc.profile, wc.model, measure, max_breakdowns=limit, dimension_filter=dimension_filter)
    for i, (d, rel) in enumerate(planned):
        tasks[f"{prefix}:{i}"] = (lambda d=d, rel=rel: DatasetDashboardService.build_breakdown(wc.profile, measure, d, rel, wc.ctx))
    return planned, skipped


def collect_breakdowns(planned, skipped, results, prefix: str = "bd") -> Tuple[List[DashboardBreakdown], List[DashboardSkippedBreakdown]]:
    built: List[DashboardBreakdown] = []
    skipped = list(skipped)
    for i, (d, _rel) in enumerate(planned):
        ok, val = results.get(f"{prefix}:{i}", (False, "not run"))
        if ok:
            built.append(val)
        else:
            skipped.append(DashboardSkippedBreakdown(dimension=f"{d.table}.{d.column}", reason=val))
    return built, skipped


def quality_summary(profile: DatasetProfile) -> Dict[str, Any]:
    findings = DatasetDashboardService.build_data_quality(profile)
    by_sev: Dict[str, int] = {}
    for t in findings:
        for f in t.findings:
            by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
    return {"tables": len(findings), "findings": sum(len(t.findings) for t in findings), "by_severity": by_sev}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- service
class DatasetWorkspaceService:

    @classmethod
    def get_overview(cls, dataset_id: str, owner_token: Optional[str] = None, limit: Optional[int] = None) -> WorkspaceOverviewResponse:
        lim = clamp_limit(limit)
        return WorkspaceCache.get_or_compute("overview", dataset_id, owner_token, (lim,),
                                             lambda: cls._compute_overview(dataset_id, owner_token, lim))

    @classmethod
    def _compute_overview(cls, dataset_id: str, owner_token: Optional[str], limit: int) -> WorkspaceOverviewResponse:
        wc = load_context(dataset_id, owner_token)
        resp = WorkspaceOverviewResponse(dataset_id=wc.profile.id, dataset_name=wc.profile.name, generated_at=_now())
        try:
            resp.quality_summary = quality_summary(wc.profile)
        except Exception as e:
            resp.section_errors["quality_summary"] = _short(e)
        if wc.model is None:
            for s in ("kpis", "trend", "breakdowns"):
                resp.section_errors[s] = wc.model_error or "semantic model unavailable"
            return resp
        if wc.primary is not None and wc.primary.column is not None:
            resp.primary_measure = metric_key(wc.primary)

        tasks: Dict[str, Callable] = {}
        for i, tbl in enumerate(wc.profile.tables):
            tasks[f"kpi:{i}"] = (lambda t=tbl: DatasetDashboardService.build_kpis_for_table(wc.profile, t, wc.measures, wc.ctx))
        planned, skipped = [], []
        if wc.primary is not None:
            tasks["trend"] = lambda: DatasetDashboardService.build_trend(wc.profile, wc.model, wc.primary, wc.ctx, grain="month")
            planned, skipped = schedule_breakdowns(wc, wc.primary, limit, tasks)
        results = run_tasks(tasks)

        kpis: List[DashboardKPI] = []
        for i in range(len(wc.profile.tables)):
            ok, val = results.get(f"kpi:{i}", (False, None))
            if ok:
                kpis.extend(val)
        resp.kpis = kpis

        if wc.primary is None:
            resp.section_errors["trend"] = resp.section_errors["breakdowns"] = "no measure in this dataset"
            return resp
        ok, val = results["trend"]
        if ok:
            resp.trend, reason = val
            if reason:
                resp.section_errors["trend"] = reason
        else:
            resp.section_errors["trend"] = val
        resp.breakdowns, resp.skipped_breakdowns = collect_breakdowns(planned, skipped, results)
        if not resp.breakdowns:
            resp.section_errors["breakdowns"] = "no suitable grouping column with a safe join path"
        return resp

    @classmethod
    def get_analytics(cls, dataset_id: str, owner_token: Optional[str] = None, metric: Optional[str] = None,
                      grain: str = "monthly", limit: Optional[int] = None) -> WorkspaceAnalyticsResponse:
        if grain not in GRAIN_PARAM:
            raise FileValidationError("grain must be one of: daily, weekly, monthly.", status_code=400)
        lim = clamp_limit(limit)
        return WorkspaceCache.get_or_compute("analytics", dataset_id, owner_token, (metric or "", grain, lim),
                                             lambda: cls._compute_analytics(dataset_id, owner_token, metric, grain, lim))

    @classmethod
    def _compute_analytics(cls, dataset_id: str, owner_token: Optional[str], metric: Optional[str], grain: str,
                           limit: int) -> WorkspaceAnalyticsResponse:
        wc = load_context(dataset_id, owner_token)
        resp = WorkspaceAnalyticsResponse(dataset_id=wc.profile.id, dataset_name=wc.profile.name, grain=grain, generated_at=_now())
        if wc.model is None:
            resp.section_errors["trend"] = resp.section_errors["breakdowns"] = wc.model_error or "semantic model unavailable"
            return resp
        resp.metrics = metric_options(wc.measures)
        by_key = {metric_key(m): m for m in wc.measures}
        if metric:
            chosen = by_key.get(metric)
            if chosen is None:
                raise FileValidationError(f"Unknown metric '{metric}'. Choose one of the listed metrics.", status_code=400)
        else:
            chosen = wc.primary
        if chosen is None:
            resp.section_errors["trend"] = resp.section_errors["breakdowns"] = "no measure in this dataset"
            return resp
        resp.metric = metric_key(chosen)
        tc = DatasetDashboardService._time_column(wc.profile, wc.model, chosen.table)
        if tc is not None:
            resp.available_grains = list(GRAIN_PARAM)
            resp.time_column = tc[0].column

        tasks: Dict[str, Callable] = {
            "trend": lambda: DatasetDashboardService.build_trend(wc.profile, wc.model, chosen, wc.ctx, grain=GRAIN_PARAM[grain]),
        }
        planned, skipped = schedule_breakdowns(wc, chosen, limit, tasks)
        results = run_tasks(tasks)
        ok, val = results["trend"]
        if ok:
            resp.trend, reason = val
            if reason:
                resp.section_errors["trend"] = reason
        else:
            resp.section_errors["trend"] = val
        resp.breakdowns, resp.skipped_breakdowns = collect_breakdowns(planned, skipped, results)
        if not resp.breakdowns:
            resp.section_errors["breakdowns"] = "no suitable grouping column with a safe join path"
        return resp


# =========================================================================== Phase 3
# Table pages, topic-group pages (Geography / Sellers / Payments / Delivery) and Data Quality.

from backend.app.schemas.dataset_workspace import (  # noqa: E402
    ColumnSummary,
    DataQualityCheck,
    WorkspaceDataQualityResponse,
    WorkspaceTableAnalysisResponse,
)
from backend.app.services.dataset_dashboard_service import (  # noqa: E402
    NUMERIC_TYPE_MARKERS,
    TIME_TYPE_MARKERS,
    quote_ident,
)
from backend.app.services.dataset_navigation_service import (  # noqa: E402
    NAV_GROUP_KEYWORDS,
    DatasetNavigationService,
    keyword_matches,
)

TABLE_BREAKDOWN_LIMIT = 8
GROUP_MEASURE_BREAKDOWNS = 3


def _is_numeric(pg_type: str) -> bool:
    return any(k in (pg_type or "").upper() for k in NUMERIC_TYPE_MARKERS)


def _is_time(pg_type: str) -> bool:
    return any(k in (pg_type or "").upper() for k in TIME_TYPE_MARKERS)


def group_matched_columns(wc: WorkspaceContext, group: str) -> List[str]:
    """Same rule as the sidebar (single source: DatasetNavigationService / NAV_GROUP_KEYWORDS)."""
    dims = None
    if wc.model is not None:
        dims = {f"{d.table}.{d.column}": [d.column, d.name] + list(d.synonyms or []) for d in wc.model.dimensions if d.column}
    nav = DatasetNavigationService.build_navigation(wc.profile, dims)
    item = next((i for i in nav.items if i.key == group), None)
    return list(item.matched_columns) if item else []


class DatasetWorkspaceTables:

    @classmethod
    def get_table_analysis(cls, dataset_id: str, owner_token: Optional[str], table: str) -> WorkspaceTableAnalysisResponse:
        return WorkspaceCache.get_or_compute("table", dataset_id, owner_token, (table,),
                                             lambda: cls._compute_table(dataset_id, owner_token, table))

    @classmethod
    def get_group_analysis(cls, dataset_id: str, owner_token: Optional[str], group: str) -> WorkspaceTableAnalysisResponse:
        if group not in NAV_GROUP_KEYWORDS:
            raise FileValidationError(f"Unknown group '{group}'. Use one of: {', '.join(NAV_GROUP_KEYWORDS)}.", status_code=400)
        return WorkspaceCache.get_or_compute("group", dataset_id, owner_token, (group,),
                                             lambda: cls._compute_group(dataset_id, owner_token, group))

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _columns_summary(tbl) -> List[ColumnSummary]:
        out = []
        for c in tbl.columns:
            show_range = _is_numeric(c.pg_type) or _is_time(c.pg_type)
            out.append(ColumnSummary(
                name=c.safe_name, pg_type=c.pg_type, role=c.role, null_pct=float(c.null_pct or 0),
                distinct_count=int(c.distinct_count or 0),
                min_val=str(c.min_val) if (show_range and c.min_val is not None) else None,
                max_val=str(c.max_val) if (show_range and c.max_val is not None) else None,
            ))
        return out

    @staticmethod
    def _finish_trend(resp, results, key="trend"):
        ok, val = results.get(key, (False, "not run"))
        if ok:
            resp.trend, reason = val
            if reason:
                resp.section_errors["trend"] = reason
        else:
            resp.section_errors["trend"] = val

    # ------------------------------------------------------------------ table page
    @classmethod
    def _compute_table(cls, dataset_id: str, owner_token: Optional[str], table: str) -> WorkspaceTableAnalysisResponse:
        wc = load_context(dataset_id, owner_token)
        tbl = next((t for t in wc.profile.tables if t.safe_name == table), None)
        if tbl is None:
            raise FileValidationError(f"Table '{table}' not found in this dataset.", status_code=404)
        resp = WorkspaceTableAnalysisResponse(dataset_id=wc.profile.id, dataset_name=wc.profile.name, table=table,
                                              row_count=tbl.row_count, columns=cls._columns_summary(tbl), generated_at=_now())
        if wc.model is None:
            for s in ("kpis", "trend", "breakdowns"):
                resp.section_errors[s] = wc.model_error or "semantic model unavailable"
            return resp
        t_measures = [m for m in wc.measures if m.table == table]
        numeric = [m for m in t_measures if m.column is not None]
        measure = select_main_measure(numeric) if numeric else next((m for m in t_measures if m.column is None), None)
        if measure is None:
            measure = MeasureDefinition(name=f"{table} rows", safe_name=f"{table}_count", table=table, column=None, aggregation="COUNT")
        resp.primary_measure = metric_key(measure)

        tasks: Dict[str, Callable] = {
            "kpis": lambda: DatasetDashboardService.build_kpis_for_table(wc.profile, tbl, wc.measures, wc.ctx),
            "trend": lambda: DatasetDashboardService.build_trend(wc.profile, wc.model, measure, wc.ctx, grain="month"),
        }
        planned, skipped = schedule_breakdowns(wc, measure, TABLE_BREAKDOWN_LIMIT, tasks)
        results = run_tasks(tasks)
        ok, val = results["kpis"]
        if ok:
            resp.kpis = val
            live_rows = next((k.value for k in val if k.column is None and k.value is not None), None)
            if live_rows is not None:
                resp.row_count = int(live_rows)
        else:
            resp.section_errors["kpis"] = val
        cls._finish_trend(resp, results)
        resp.breakdowns, resp.skipped_breakdowns = collect_breakdowns(planned, skipped, results)
        if not resp.breakdowns:
            resp.section_errors["breakdowns"] = "no suitable grouping column with a safe join path"
        return resp

    # ------------------------------------------------------------------ group page
    @classmethod
    def _compute_group(cls, dataset_id: str, owner_token: Optional[str], group: str) -> WorkspaceTableAnalysisResponse:
        wc = load_context(dataset_id, owner_token)
        matched = group_matched_columns(wc, group)
        if not matched:
            kws = ", ".join(NAV_GROUP_KEYWORDS[group]["keywords"])
            raise FileValidationError(f"This dataset has no {NAV_GROUP_KEYWORDS[group]['label']} columns (looked for: {kws}).", status_code=404)
        primary_table = wc.primary.table if wc.primary is not None else wc.profile.tables[0].safe_name
        tbl = next((t for t in wc.profile.tables if t.safe_name == primary_table), wc.profile.tables[0])
        resp = WorkspaceTableAnalysisResponse(dataset_id=wc.profile.id, dataset_name=wc.profile.name, table=tbl.safe_name,
                                              group=group, row_count=tbl.row_count, matched_columns=matched, generated_at=_now())
        matched_set = set(matched)
        resp.columns = [c for t in wc.profile.tables for c in cls._columns_summary(t)
                        if f"{t.safe_name}.{c.name}" in matched_set]
        if wc.model is None:
            for s in ("kpis", "trend", "breakdowns"):
                resp.section_errors[s] = wc.model_error or "semantic model unavailable"
            return resp

        group_measures = [m for m in wc.measures if m.column is not None and f"{m.table}.{m.column}" in matched_set]
        primary = wc.primary
        if primary is not None and primary.column is not None:
            resp.primary_measure = metric_key(primary)

        tasks: Dict[str, Callable] = {}
        # KPIs: the dataset's primary measure plus every numeric column of this group
        kpi_measures = ([primary] if primary is not None and primary.column is not None else []) + \
                       [m for m in group_measures if primary is None or metric_key(m) != metric_key(primary)]
        by_table: Dict[str, List[MeasureDefinition]] = {}
        for m in kpi_measures:
            by_table.setdefault(m.table, []).append(m)
        for i, (t_name, ms) in enumerate(by_table.items()):
            t_prof = next(t for t in wc.profile.tables if t.safe_name == t_name)
            tasks[f"kpi:{i}"] = (lambda t=t_prof, ms=ms: [
                k for k in DatasetDashboardService.build_kpis_for_table(wc.profile, t, ms, wc.ctx) if k.column is not None])
        # Trend: first numeric group column (e.g. delivery_days); otherwise none
        trend_measure = group_measures[0] if group_measures else None
        if trend_measure is not None:
            tasks["trend"] = lambda: DatasetDashboardService.build_trend(wc.profile, wc.model, trend_measure, wc.ctx, grain="month")
        # Breakdowns: primary measure by each group dimension (e.g. revenue by city / payment method)
        planned_main, skipped_main = ([], [])
        if primary is not None:
            planned_main, skipped_main = schedule_breakdowns(
                wc, primary, TABLE_BREAKDOWN_LIMIT, tasks,
                dimension_filter=lambda d: f"{d.table}.{d.column}" in matched_set, prefix="bdm")
        # ... and each numeric group column by the dataset's other suitable dimensions
        planned_g: List[Tuple[MeasureDefinition, list]] = []
        skipped_g: List[DashboardSkippedBreakdown] = []
        for gi, gm in enumerate(group_measures[:2]):
            p, s = schedule_breakdowns(wc, gm, GROUP_MEASURE_BREAKDOWNS, tasks,
                                       dimension_filter=lambda d: f"{d.table}.{d.column}" not in matched_set, prefix=f"bdg{gi}")
            planned_g.append((gm, p))
            skipped_g.extend(s)
        results = run_tasks(tasks)

        kpis: List[DashboardKPI] = []
        for i in range(len(by_table)):
            ok, val = results.get(f"kpi:{i}", (False, None))
            if ok:
                kpis.extend(val)
        resp.kpis = kpis
        if trend_measure is not None:
            cls._finish_trend(resp, results)
        else:
            resp.section_errors["trend"] = f"no numeric {NAV_GROUP_KEYWORDS[group]['label'].lower()} column to trend; see the breakdowns"
        built, skipped = collect_breakdowns(planned_main, skipped_main, results, prefix="bdm")
        for gi, (gm, p) in enumerate(planned_g):
            b2, _s2 = collect_breakdowns(p, [], results, prefix=f"bdg{gi}")
            built.extend(b2)
        resp.breakdowns = built
        # de-duplicate skip reasons (same column can be skipped for several measures)
        seen, uniq = set(), []
        for s in skipped + skipped_g:
            if s.dimension not in seen:
                seen.add(s.dimension)
                uniq.append(s)
        resp.skipped_breakdowns = uniq
        if not built:
            resp.section_errors["breakdowns"] = "no breakdown with a safe join path (confirm relationships on the Datasets page)"
        return resp


# --------------------------------------------------------------------------- data quality
def numeric_measure_columns(wc: WorkspaceContext, tbl) -> set:
    """Numeric columns that hold quantities: semantic measures, numeric columns profiled as role
    'measure', and fractional numeric columns (covers a unique 'amount' the profiler took for a key)."""
    cols = {m.column for m in wc.measures if m.table == tbl.safe_name and m.column is not None}
    cols |= {c.safe_name for c in tbl.columns if c.role == "measure" and _is_numeric(c.pg_type)}
    # Fractional numeric columns are quantities even when the profiler labelled them 'id' because
    # every value happened to be unique (integer id columns stay excluded).
    cols |= {c.safe_name for c in tbl.columns
             if any(k in (c.pg_type or "").upper() for k in ("NUMERIC", "DECIMAL", "FLOAT", "DOUBLE", "REAL"))}
    return {c for c in cols if any(col.safe_name == c and _is_numeric(col.pg_type) for col in tbl.columns)}


class DatasetWorkspaceQuality:
    """Real, deterministic checks computed live on the dataset (not just the stored profile)."""

    @classmethod
    def get_data_quality(cls, dataset_id: str, owner_token: Optional[str]) -> WorkspaceDataQualityResponse:
        return WorkspaceCache.get_or_compute("data_quality", dataset_id, owner_token, (),
                                             lambda: cls._compute(dataset_id, owner_token))

    @staticmethod
    def key_columns(tbl) -> List[str]:
        """Candidate PK plus id-like columns named after the table (e.g. orders.order_id, or 'id')."""
        stem = tbl.safe_name.rstrip("s")
        keys = [tbl.candidate_pk] if tbl.candidate_pk else []
        for c in tbl.columns:
            if c.safe_name in keys:
                continue
            if c.safe_name == "id" or (c.role == "id" and c.safe_name in (f"{stem}_id", f"{tbl.safe_name}_id")):
                keys.append(c.safe_name)
        return keys

    @classmethod
    def _table_task(cls, wc: WorkspaceContext, tbl) -> Dict[str, Any]:
        """One validated query per table: row count, key duplicates/nulls, non-null counts,
        negative values on numeric measures, future dates on real date/time columns."""
        measure_cols = numeric_measure_columns(wc, tbl)
        parts = ["COUNT(*) AS n"]
        spec: List[Tuple[str, str, str]] = []  # (alias, kind, column)
        for i, k in enumerate(cls.key_columns(tbl)):
            parts.append(f"COUNT(DISTINCT {quote_ident(k)}) AS {quote_ident(f'kd{i}')}")
            parts.append(f"COUNT({quote_ident(k)}) AS {quote_ident(f'kn{i}')}")
            spec.append((str(i), "key", k))
        for i, c in enumerate(tbl.columns):
            q = quote_ident(c.safe_name)
            parts.append(f"COUNT({q}) AS {quote_ident(f'c{i}')}")
            spec.append((str(i), "col", c.safe_name))
            if c.safe_name in measure_cols and _is_numeric(c.pg_type):
                parts.append(f"SUM(CASE WHEN {q} < 0 THEN 1 ELSE 0 END) AS {quote_ident(f'neg{i}')}")
                spec.append((str(i), "neg", c.safe_name))
            if _is_time(c.pg_type):
                parts.append(f"SUM(CASE WHEN {q} > CURRENT_DATE THEN 1 ELSE 0 END) AS {quote_ident(f'fut{i}')}")
                spec.append((str(i), "fut", c.safe_name))
        sql_text = f"SELECT {', '.join(parts)} FROM {quote_ident(wc.profile.schema_name)}.{quote_ident(tbl.safe_name)}"
        rows = DatasetDashboardService._run(sql_text, wc.ctx, wc.profile.schema_name)
        return {"row": rows[0] if rows else {}, "spec": spec}

    @classmethod
    def _orphan_task(cls, wc: WorkspaceContext, rel) -> int:
        S = quote_ident(wc.profile.schema_name)
        sql_text = (
            f"SELECT COUNT(*) AS orphans FROM {S}.{quote_ident(rel.child_table)} AS {quote_ident('c')} "
            f"LEFT JOIN {S}.{quote_ident(rel.parent_table)} AS {quote_ident('p')} "
            f"ON {quote_ident('c')}.{quote_ident(rel.child_column)} = {quote_ident('p')}.{quote_ident(rel.parent_column)} "
            f"WHERE {quote_ident('c')}.{quote_ident(rel.child_column)} IS NOT NULL "
            f"AND {quote_ident('p')}.{quote_ident(rel.parent_column)} IS NULL"
        )
        rows = DatasetDashboardService._run(sql_text, wc.ctx, wc.profile.schema_name)
        return int((rows[0] if rows else {}).get("orphans") or 0)

    @classmethod
    def _join_safety_task(cls, wc: WorkspaceContext, rel, measure: MeasureDefinition) -> Tuple[float, float]:
        S = quote_ident(wc.profile.schema_name)
        col = quote_ident(measure.column)
        before = DatasetDashboardService._run(
            f"SELECT SUM({col}) AS v FROM {S}.{quote_ident(rel.child_table)}", wc.ctx, wc.profile.schema_name)
        after = DatasetDashboardService._run(
            f"SELECT SUM({quote_ident('f')}.{col}) AS v FROM {S}.{quote_ident(rel.child_table)} AS {quote_ident('f')} "
            f"LEFT JOIN {S}.{quote_ident(rel.parent_table)} AS {quote_ident('d')} "
            f"ON {quote_ident('f')}.{quote_ident(rel.child_column)} = {quote_ident('d')}.{quote_ident(rel.parent_column)}",
            wc.ctx, wc.profile.schema_name)
        b = float((before[0] if before else {}).get("v") or 0.0)
        a = float((after[0] if after else {}).get("v") or 0.0)
        return b, a

    @classmethod
    def _status_task(cls, wc: WorkspaceContext, table: str, column: str) -> Dict[str, int]:
        q = quote_ident(column)
        rows = DatasetDashboardService._run(
            f"SELECT CAST({q} AS TEXT) AS k, COUNT(*) AS n FROM {quote_ident(wc.profile.schema_name)}.{quote_ident(table)} "
            f"GROUP BY 1 ORDER BY 2 DESC LIMIT 20", wc.ctx, wc.profile.schema_name)
        return {str(r.get("k") if r.get("k") is not None else "(blank)"): int(r.get("n") or 0) for r in rows}

    @classmethod
    def _compute(cls, dataset_id: str, owner_token: Optional[str]) -> WorkspaceDataQualityResponse:
        wc = load_context(dataset_id, owner_token)
        p = wc.profile
        resp = WorkspaceDataQualityResponse(dataset_id=p.id, dataset_name=p.name, generated_at=_now())
        confirmed = [r for r in p.relationships if r.confirmed]

        # status-like column for the breakdown (first match, deterministic order)
        status_col = next(((t.safe_name, c.safe_name) for t in p.tables for c in t.columns
                           if keyword_matches(c.safe_name, "status") and not _is_numeric(c.pg_type)), None)

        tasks: Dict[str, Callable] = {}
        for ti, tbl in enumerate(p.tables):
            tasks[f"table:{ti}"] = (lambda t=tbl: cls._table_task(wc, t))
        for ri, rel in enumerate(confirmed):
            tasks[f"orphans:{ri}"] = (lambda r=rel: cls._orphan_task(wc, r))
            # join safety: first SUM measure on the child (fact) side of a safe N:1 relationship
            safe_rel, _ = DatasetDashboardService.find_safe_join(p, rel.child_table, rel.parent_table)
            m = next((m for m in wc.measures if m.table == rel.child_table and m.column is not None
                      and m.aggregation.upper() == "SUM"), None)
            if m is None:  # e.g. the profiler picked the amount column as a candidate key
                child = next(t for t in p.tables if t.safe_name == rel.child_table)
                col = next(iter(sorted(numeric_measure_columns(wc, child))), None)
                if col is not None:
                    m = MeasureDefinition(name=col, safe_name=f"{child.safe_name}_{col}", table=child.safe_name, column=col, aggregation="SUM")
            if safe_rel is not None and m is not None:
                tasks[f"join:{ri}"] = (lambda r=rel, m=m: cls._join_safety_task(wc, r, m))
        if status_col:
            tasks["status"] = lambda: cls._status_task(wc, *status_col)
        results = run_tasks(tasks)

        checks: List[DataQualityCheck] = []
        dup_total, neg_total, fut_total = 0, 0, 0
        for ti, tbl in enumerate(p.tables):
            ok, val = results[f"table:{ti}"]
            if not ok:
                resp.section_errors[f"table:{tbl.safe_name}"] = val
                checks.append(DataQualityCheck(check="table_scan", table=tbl.safe_name, status="SKIPPED", detail=val))
                continue
            row, spec = val["row"], val["spec"]
            n = int(row.get("n") or 0)
            resp.table_row_counts[tbl.safe_name] = n
            for idx, kind, col in spec:
                if kind == "key":
                    distinct, nonnull = int(row.get(f"kd{idx}") or 0), int(row.get(f"kn{idx}") or 0)
                    dups, nulls = nonnull - distinct, n - nonnull
                    dup_total += dups + nulls
                    checks.append(DataQualityCheck(
                        check="primary_key", table=tbl.safe_name, column=col, status="PASS" if dups == 0 and nulls == 0 else "FAIL",
                        value=float(dups + nulls), detail=f"{dups} duplicate and {nulls} missing key values in {n} rows"))
                elif kind == "col":
                    missing = n - int(row.get(f"c{idx}") or 0)
                    if missing > 0:
                        resp.missing_value_summary[f"{tbl.safe_name}.{col}"] = missing
                    checks.append(DataQualityCheck(
                        check="missing_values", table=tbl.safe_name, column=col, status="PASS" if missing == 0 else "WARN",
                        value=float(missing), detail=f"{missing} of {n} values missing ({(100.0 * missing / n) if n else 0:.1f}%)"))
                elif kind == "neg":
                    neg = int(row.get(f"neg{idx}") or 0)
                    neg_total += neg
                    checks.append(DataQualityCheck(
                        check="negative_values", table=tbl.safe_name, column=col, status="PASS" if neg == 0 else "WARN",
                        value=float(neg), detail=f"{neg} negative values"))
                elif kind == "fut":
                    fut = int(row.get(f"fut{idx}") or 0)
                    fut_total += fut
                    checks.append(DataQualityCheck(
                        check="future_dates", table=tbl.safe_name, column=col, status="PASS" if fut == 0 else "WARN",
                        value=float(fut), detail=f"{fut} dates after today"))

        orphan_total, fk_ran = 0, 0
        join_ran, join_max_diff = 0, 0.0
        for ri, rel in enumerate(confirmed):
            label = f"{rel.child_table}.{rel.child_column} -> {rel.parent_table}.{rel.parent_column}"
            ok, val = results[f"orphans:{ri}"]
            if ok:
                fk_ran += 1
                orphan_total += val
                checks.append(DataQualityCheck(check="foreign_key", table=rel.child_table, column=rel.child_column,
                                               status="PASS" if val == 0 else "FAIL", value=float(val),
                                               detail=f"{val} orphan rows for {label}"))
            else:
                checks.append(DataQualityCheck(check="foreign_key", table=rel.child_table, column=rel.child_column,
                                               status="SKIPPED", detail=val))
            if f"join:{ri}" in results:
                ok, val = results[f"join:{ri}"]
                if ok:
                    before, after = val
                    diff = abs(after - before)
                    join_ran += 1
                    join_max_diff = max(join_max_diff, diff)
                    checks.append(DataQualityCheck(check="join_safety", table=rel.child_table, column=None,
                                                   status="PASS" if diff < 0.005 else "FAIL", value=round(diff, 4),
                                                   detail=f"SUM before join {before:,.2f} vs after {label} {after:,.2f}"))
                else:
                    checks.append(DataQualityCheck(check="join_safety", table=rel.child_table, status="SKIPPED", detail=val))

        if status_col:
            ok, val = results["status"]
            if ok:
                resp.order_status_breakdown = val
                resp.status_column = f"{status_col[0]}.{status_col[1]}"
            else:
                resp.section_errors["status_breakdown"] = val

        n_tables = len(resp.table_row_counts)
        resp.primary_key_uniqueness = (f"PASS (0 duplicates across {n_tables} tables)" if dup_total == 0
                                       else f"FAIL ({dup_total} duplicate or missing key values)")
        resp.foreign_key_integrity = ("SKIPPED (no confirmed relationships; confirm them on the Datasets page)" if not confirmed
                                      else (f"PASS (0 orphans across {fk_ran} confirmed relationships)" if orphan_total == 0
                                            else f"FAIL ({orphan_total} orphan rows)"))
        resp.domain_bounds_status = (f"PASS (0 negative values, 0 future dates)" if neg_total == 0 and fut_total == 0
                                     else f"WARN ({neg_total} negative values, {fut_total} future dates)")
        resp.join_safety_status = ("SKIPPED (no confirmed N:1 relationship with a summable measure)" if join_ran == 0
                                   else (f"PASS ({join_max_diff:.2f} discrepancy across {join_ran} joins)" if join_max_diff < 0.005
                                         else f"FAIL ({join_max_diff:,.2f} discrepancy)"))
        resp.checks = checks
        statuses = {c.status for c in checks}
        resp.audit_status = "FAIL" if "FAIL" in statuses else ("WARN" if "WARN" in statuses else "PASS")
        resp.anomalies_flagged = [f"{c.check}: {c.table}{'.' + c.column if c.column else ''}: {c.detail}"
                                  for c in checks if c.status in ("FAIL", "WARN")][:50]
        return resp
