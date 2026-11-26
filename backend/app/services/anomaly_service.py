import os
import sys
import logging
import uuid
import threading
import time
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from datetime import datetime
import numpy as np
import pandas as pd
from sqlalchemy import text

try:
    from statsmodels.tsa.seasonal import STL
    STL_AVAILABLE = True
except ImportError:
    STL_AVAILABLE = False

try:
    from sklearn.ensemble import IsolationForest
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

from backend.app.database import readonly_engine
from backend.app.fixture_guard import assert_database_available, is_fixture_mode_allowed
from backend.app.exceptions import DatabaseUnavailableError
from backend.app.schemas.anomaly import AnomalyItem, AnomalyTimeSeriesPoint, AnomalyListResponse, AnomalyScanResponse

logger = logging.getLogger(__name__)

# Known historical business, retail & promotional events for Olist Brazil
# Stored strictly as: date/period -> {"name": str, "type": str} (no hardcoded revenue/financial figures)
KNOWN_EVENTS: Dict[str, Dict[str, str]] = {
    "2017-11-24": {"name": "Black Friday 2017", "type": "promotional_peak"},
    "2017-11-25": {"name": "Black Friday Weekend 2017", "type": "promotional_peak"},
    "2017-11-26": {"name": "Black Friday Weekend 2017", "type": "promotional_peak"},
    "2017-11-27": {"name": "Cyber Monday 2017", "type": "promotional_peak"},
    "2017-11-20": {"name": "Black Friday Week 2017", "type": "promotional_peak"},
    "2017-W47": {"name": "Black Friday Week 2017", "type": "promotional_peak"},
    "2017-11-27": {"name": "Cyber Week 2017", "type": "promotional_peak"},
    "2017-W48": {"name": "Cyber Week 2017", "type": "promotional_peak"},
    "2017-12-24": {"name": "Christmas Eve 2017", "type": "holiday_slowdown"},
    "2017-12-25": {"name": "Christmas Day 2017", "type": "holiday_slowdown"},
    "2018-01-01": {"name": "New Year's Day 2018", "type": "holiday_slowdown"},
    "2018-05-07": {"name": "Mother's Day Shopping Week 2018", "type": "seasonal_gifting"},
    "2018-05-13": {"name": "Mother's Day Brazil 2018", "type": "seasonal_gifting"},
    "2018-W19": {"name": "Mother's Day Shopping Week 2018", "type": "seasonal_gifting"},
    "2018-06-11": {"name": "Valentine's Shopping Week 2018", "type": "seasonal_gifting"},
    "2018-06-12": {"name": "Valentine's Day Brazil (Dia dos Namorados)", "type": "seasonal_gifting"},
    "2018-W24": {"name": "Valentine's Shopping Week 2018", "type": "seasonal_gifting"}
}


def format_known_event(period: str) -> Optional[str]:
    """Format known event candidate strictly from catalog metadata without hardcoded values."""
    ev = KNOWN_EVENTS.get(period)
    if not ev:
        return None
    return f"{ev['name']} ({ev['type']})"


class AnomalyService:
    """
    Deterministic Anomaly Detection Engine for InsightForge.
    Constructs robust statistical and machine learning anomaly detection over
    e-commerce time series without LLM generation.
    """

    CACHE_TTL: int = 300  # 5-minute server-side cache
    _series_cache: Dict[Tuple[str, str], Tuple[float, pd.DataFrame]] = {}  # (dataset_id, grain) -> (timestamp, df)
    _detect_cache: Dict[Tuple[str, str, str, Optional[str]], Tuple[float, Any]] = {}  # (dataset_id, grain, metric, severity) -> (timestamp, res)
    _cache_lock = threading.Lock()

    RATIO_METRICS = {"aov", "on_time_delivery_rate", "avg_review_score"}
    COLD_START_DAYS = 30
    DEFAULT_MIN_ORDERS = 30

    @classmethod
    def clear_cache(cls, dataset_id: Optional[str] = None) -> None:
        """
        Invalidates cached time-series and anomaly results.
        If dataset_id is provided, purges only entries for that dataset.
        Otherwise purges all caches.
        """
        with cls._cache_lock:
            if dataset_id:
                cls._series_cache = {k: v for k, v in cls._series_cache.items() if k[0] != dataset_id}
                cls._detect_cache = {k: v for k, v in cls._detect_cache.items() if k[0] != dataset_id}
            else:
                cls._series_cache.clear()
                cls._detect_cache.clear()

    @classmethod
    def get_time_series(cls, grain: str = "daily", dataset_id: str = "olist-demo") -> pd.DataFrame:
        """
        Extract delivered order daily or weekly metrics from PostgreSQL.
        Trims sparse early-2016 data (before 2017-01-01) and incomplete final records (after 2018-08-31).
        Utilizes 5-minute server-side cache and pre-filtered CTE aggregation.
        Cache key is scoped by (dataset_id, grain) for multi-tenant dataset isolation.
        """
        now = time.time()
        cache_key = (dataset_id, grain)
        if is_fixture_mode_allowed():
            return cls._get_canonical_fixture_series(grain=grain)
        with cls._cache_lock:
            if cache_key in cls._series_cache:
                cached_time, cached_df = cls._series_cache[cache_key]
                if now - cached_time < cls.CACHE_TTL:
                    return cached_df.copy()

        try:
            date_trunc = "day" if grain == "daily" else "week"
            query = text(f"""
                WITH filtered_orders AS (
                    SELECT 
                        order_id,
                        DATE_TRUNC('{date_trunc}', order_purchase_timestamp)::DATE AS period_date,
                        CASE WHEN order_delivered_customer_date <= order_estimated_delivery_date THEN 1 ELSE 0 END AS on_time
                    FROM insightforge.orders
                    WHERE order_status = 'delivered'
                      AND order_purchase_timestamp >= '2017-01-01'
                      AND order_purchase_timestamp < '2018-09-01'
                ),
                daily_agg AS (
                    SELECT 
                        fo.period_date,
                        SUM(oi.price + oi.freight_value) AS gross_revenue,
                        COUNT(DISTINCT fo.order_id) AS order_count,
                        ROUND(SUM(oi.price + oi.freight_value) / NULLIF(COUNT(DISTINCT fo.order_id), 0), 2) AS aov,
                        ROUND(AVG(fo.on_time) * 100.0, 2) AS on_time_delivery_rate
                    FROM filtered_orders fo
                    JOIN insightforge.order_items oi ON fo.order_id = oi.order_id
                    GROUP BY fo.period_date
                ),
                reviews AS (
                    SELECT 
                        fo.period_date,
                        ROUND(AVG(r.review_score), 2) AS avg_review_score
                    FROM filtered_orders fo
                    JOIN insightforge.order_reviews r ON fo.order_id = r.order_id
                    GROUP BY fo.period_date
                )
                SELECT 
                    d.period_date,
                    d.gross_revenue,
                    d.order_count,
                    d.aov,
                    d.on_time_delivery_rate,
                    rev.avg_review_score
                FROM daily_agg d
                LEFT JOIN reviews rev ON d.period_date = rev.period_date
                ORDER BY d.period_date ASC;
            """)
            with readonly_engine.connect() as conn:
                df = pd.read_sql(query, conn)
            if not df.empty:
                df["period"] = df["period_date"].astype(str)
                with cls._cache_lock:
                    cls._series_cache[cache_key] = (time.time(), df.copy())
                return df
        except Exception as e:
            assert_database_available(e, f"anomaly_series_{grain}")
            logger.warning(f"Database unavailable for anomaly series ({e}). Using canonical fixture.")

        return cls._get_canonical_fixture_series(grain=grain)

    @classmethod
    def _get_canonical_fixture_series(cls, grain: str = "daily") -> pd.DataFrame:
        """
        Canonical benchmark series derived from Olist e-commerce data (2017-01 to 2018-08).
        Includes the real historic 2017-11-24 Black Friday spike (R$ 158,000+ vs ~R$ 25,000 baseline).
        """
        if not is_fixture_mode_allowed():
            raise DatabaseUnavailableError("Fixture fallback is disallowed when USE_FIXTURES is not enabled.")
        np.random.seed(42)
        if grain == "daily":
            dates = pd.date_range("2017-01-01", "2018-08-31", freq="D")
            n = len(dates)
            
            # Baseline parameters
            base_orders = 130.0 + np.linspace(0, 70, n) + 20 * np.sin(np.linspace(0, 10 * np.pi, n))
            # Day-of-week seasonality (weekends have lower sales)
            dow_factor = np.array([1.1, 1.15, 1.1, 1.05, 0.95, 0.75, 0.85])[dates.dayofweek]
            orders = (base_orders * dow_factor).astype(int)
            aov = 155.0 + np.random.normal(0, 8, n)
            revenue = orders * aov
            on_time = 92.0 + np.random.normal(0, 2.0, n)
            csat = 4.15 + np.random.normal(0, 0.1, n)

            df = pd.DataFrame({
                "period_date": dates,
                "period": dates.strftime("%Y-%m-%d"),
                "order_count": orders,
                "gross_revenue": np.round(revenue, 2),
                "aov": np.round(aov, 2),
                "on_time_delivery_rate": np.round(np.clip(on_time, 70.0, 99.0), 2),
                "avg_review_score": np.round(np.clip(csat, 3.0, 5.0), 2)
            })

            # Inject real Black Friday peak on 2017-11-24
            bf_idx = df[df["period"] == "2017-11-24"].index
            if not bf_idx.empty:
                df.loc[bf_idx, "order_count"] = 1140
                df.loc[bf_idx, "gross_revenue"] = 176940.50
                df.loc[bf_idx, "aov"] = 155.21

            # Inject Cyber Monday peak on 2017-11-27
            cm_idx = df[df["period"] == "2017-11-27"].index
            if not cm_idx.empty:
                df.loc[cm_idx, "order_count"] = 520
                df.loc[cm_idx, "gross_revenue"] = 82400.00

            # Inject a logistics delay anomaly in March 2018 (Carrier strike simulation)
            delay_idx = df[df["period"] == "2018-03-15"].index
            if not delay_idx.empty:
                df.loc[delay_idx, "on_time_delivery_rate"] = 64.20
                df.loc[delay_idx, "avg_review_score"] = 3.20

            return df
        else:
            # Weekly grain
            weeks = pd.date_range("2017-01-01", "2018-08-31", freq="W-MON")
            n = len(weeks)
            base_orders = 1000 + np.linspace(0, 500, n)
            orders = base_orders.astype(int)
            aov = 158.0 + np.random.normal(0, 5, n)
            revenue = orders * aov
            on_time = 92.5 + np.random.normal(0, 1.5, n)
            csat = 4.16 + np.random.normal(0, 0.08, n)

            df = pd.DataFrame({
                "period_date": weeks,
                "period": [f"{w.year}-W{w.isocalendar().week:02d}" for w in weeks],
                "order_count": orders,
                "gross_revenue": np.round(revenue, 2),
                "aov": np.round(aov, 2),
                "on_time_delivery_rate": np.round(np.clip(on_time, 75.0, 99.0), 2),
                "avg_review_score": np.round(np.clip(csat, 3.2, 5.0), 2)
            })

            # Black Friday Week 2017 (Week 47)
            bf_w_idx = df[df["period"] == "2017-W47"].index
            if not bf_w_idx.empty:
                df.loc[bf_w_idx, "order_count"] = 3450
                df.loc[bf_w_idx, "gross_revenue"] = 548900.00

            return df

    @classmethod
    def detect_rolling_zscore(
        cls,
        df: pd.DataFrame,
        metric: str = "gross_revenue",
        window: int = 14,
        threshold: float = 2.5
    ) -> List[AnomalyItem]:
        """
        Method (a): Rolling robust z-score using median and Median Absolute Deviation (MAD).
        Formula: z = 0.6745 * (x - median) / MAD
        Filters out cold start (first 30 days) and small samples (< 30 orders) for ratio metrics.
        """
        series = df[metric].astype(float)
        periods = df["period"].tolist()
        anomalies: List[AnomalyItem] = []

        # Cold start filtering: only apply if series has date column and length > cold start window
        cold_cutoff = None
        period_dates = None
        date_col = "period_date" if "period_date" in df.columns else ("period" if "period" in df.columns else None)
        if date_col is not None and len(df) >= 90:
            try:
                period_dates = pd.to_datetime(df[date_col])
                cold_cutoff = period_dates.min() + pd.Timedelta(days=cls.COLD_START_DAYS)
            except Exception:
                cold_cutoff = None
                period_dates = None

        order_counts = df["order_count"].astype(int) if "order_count" in df.columns else None

        rolling_median = series.rolling(window=window, min_periods=max(3, window // 2), center=False).median()
        rolling_mad = series.rolling(window=window, min_periods=max(3, window // 2), center=False).apply(
            lambda x: np.median(np.abs(x - np.median(x))) if len(x) > 0 else 0.0,
            raw=True
        )

        for i in range(len(series)):
            # Cold start filtering
            if cold_cutoff is not None and period_dates is not None and period_dates.iloc[i] < cold_cutoff:
                continue
            # Small sample filtering for ratio metrics
            if metric in cls.RATIO_METRICS and order_counts is not None and order_counts.iloc[i] < cls.DEFAULT_MIN_ORDERS:
                continue

            obs = float(series.iloc[i])
            med = float(rolling_median.iloc[i]) if not np.isnan(rolling_median.iloc[i]) else obs
            mad = float(rolling_mad.iloc[i]) if not np.isnan(rolling_mad.iloc[i]) else 0.0

            if mad < 1e-4:
                mad = max(0.05 * abs(med), 1.0)

            z = 0.6745 * (obs - med) / mad
            abs_z = abs(z)

            if abs_z >= threshold:
                severity = "high" if abs_z >= 8.0 else ("medium" if abs_z >= 4.0 else "low")
                direction = "spike" if z > 0 else "drop"
                period_str = periods[i]
                event = format_known_event(period_str)
                classification = event if event else "statistical_outlier"

                anomalies.append(AnomalyItem(
                    metric=metric,
                    dimension="overall",
                    period=period_str,
                    observed=round(obs, 2),
                    expected=round(med, 2),
                    deviation_score=round(float(z), 2),
                    severity=severity,
                    direction=direction,
                    method="rolling_zscore",
                    known_event_candidate=event,
                    classification=classification
                ))

        return anomalies

    @classmethod
    def detect_stl_residuals(
        cls,
        df: pd.DataFrame,
        metric: str = "gross_revenue",
        period: int = 7,
        threshold: float = 2.5
    ) -> List[AnomalyItem]:
        """
        Method (b): STL Decomposition (Seasonal and Trend decomposition using Loess).
        Flags statistical outliers in the residual noise component.
        Filters out cold start (first 30 days) and small samples (< 30 orders) for ratio metrics.
        """
        if not STL_AVAILABLE or len(df) < period * 2:
            return []

        series = df[metric].astype(float)
        periods = df["period"].tolist()
        anomalies: List[AnomalyItem] = []

        cold_cutoff = None
        period_dates = None
        date_col = "period_date" if "period_date" in df.columns else ("period" if "period" in df.columns else None)
        if date_col is not None and len(df) >= 90:
            try:
                period_dates = pd.to_datetime(df[date_col])
                cold_cutoff = period_dates.min() + pd.Timedelta(days=cls.COLD_START_DAYS)
            except Exception:
                cold_cutoff = None
                period_dates = None

        order_counts = df["order_count"].astype(int) if "order_count" in df.columns else None

        try:
            stl = STL(series, period=period, robust=True)
            res = stl.fit()
            resid = res.resid
            trend = res.trend
            seasonal = res.seasonal
            expected = trend + seasonal

            resid_median = np.median(resid)
            resid_mad = np.median(np.abs(resid - resid_median))
            scale = resid_mad * 1.4826 if resid_mad > 1e-4 else np.std(resid)
            if scale < 1e-4:
                scale = 1.0

            norm_resid = (resid - resid_median) / scale

            for i in range(len(series)):
                # Cold start filtering
                if cold_cutoff is not None and period_dates is not None and period_dates.iloc[i] < cold_cutoff:
                    continue
                # Small sample filtering for ratio metrics
                if metric in cls.RATIO_METRICS and order_counts is not None and order_counts.iloc[i] < cls.DEFAULT_MIN_ORDERS:
                    continue

                score = float(norm_resid.iloc[i])
                if abs(score) >= threshold:
                    obs = float(series.iloc[i])
                    exp = float(expected.iloc[i])
                    period_str = periods[i]
                    event = format_known_event(period_str)
                    classification = event if event else "statistical_outlier"

                    severity = "high" if abs(score) >= 8.0 else ("medium" if abs(score) >= 4.0 else "low")
                    direction = "spike" if score > 0 else "drop"

                    anomalies.append(AnomalyItem(
                        metric=metric,
                        dimension="overall",
                        period=period_str,
                        observed=round(obs, 2),
                        expected=round(exp, 2),
                        deviation_score=round(score, 2),
                        severity=severity,
                        direction=direction,
                        method="stl_residual",
                        known_event_candidate=event,
                        classification=classification
                    ))
        except Exception as e:
            logger.debug(f"STL decomposition skipped: {e}")

        return anomalies

    @classmethod
    def detect_iqr_dimension_slices(
        cls,
        df: Optional[pd.DataFrame] = None,
        metric: str = "gross_revenue",
        threshold: float = 1.5
    ) -> List[AnomalyItem]:
        """
        Method (c): Interquartile Range (IQR) outlier detection across dimension slices
        (product categories, regional customer states, and merchant sellers).
        """
        anomalies: List[AnomalyItem] = []
        if df is not None:
            slice_df = df
        else:
            try:
                # Query state revenue slice from delivered orders
                query = text("""
                    SELECT 
                        c.customer_state AS dim_name,
                        SUM(oi.price + oi.freight_value) AS total_revenue
                    FROM insightforge.orders o
                    JOIN insightforge.order_items oi ON o.order_id = oi.order_id
                    JOIN insightforge.customers c ON o.customer_id = c.customer_id
                    WHERE o.order_status = 'delivered'
                    GROUP BY c.customer_state
                    HAVING SUM(oi.price + oi.freight_value) > 0;
                """)
                with readonly_engine.connect() as conn:
                    slice_df = pd.read_sql(query, conn)
            except Exception as e:
                assert_database_available(e, "iqr_dimension_slices")
                slice_df = pd.DataFrame([
                    ("SP", 5041040.67), ("RJ", 1709477.34), ("MG", 1585308.03), ("RS", 750000.00),
                    ("PR", 680000.00), ("SC", 520000.00), ("BA", 500000.00), ("DF", 300000.00),
                    ("ES", 270000.00), ("GO", 290000.00), ("PE", 250000.00), ("CE", 220000.00),
                    ("PA", 180000.00), ("MT", 160000.00), ("MA", 120000.00), ("MS", 110000.00),
                    ("PB", 115000.00), ("PI", 86000.00), ("RN", 83000.00), ("AL", 80000.00),
                    ("SE", 58000.00), ("TO", 49000.00), ("RO", 46000.00), ("AM", 23000.00),
                    ("AC", 16000.00), ("AP", 13000.00), ("RR", 7000.00)
                ], columns=["dim_name", "total_revenue"])

        if not slice_df.empty:
            rev_col = "total_revenue" if "total_revenue" in slice_df.columns else slice_df.columns[1]
            dim_col = "dim_name" if "dim_name" in slice_df.columns else slice_df.columns[0]
            revs = slice_df[rev_col].astype(float)
            q1 = revs.quantile(0.25)
            q3 = revs.quantile(0.75)
            iqr = q3 - q1
            median = revs.median()

            upper_bound = q3 + threshold * iqr
            lower_bound = max(0.0, q1 - threshold * iqr)

            for _, row in slice_df.iterrows():
                val = float(row[rev_col])
                name = str(row[dim_col])
                if val > upper_bound or (lower_bound > 0 and val < lower_bound):
                    dev_score = round((val - median) / (iqr if iqr > 0 else 1.0), 2)
                    direction = "spike" if val > upper_bound else "drop"
                    severity = "high" if abs(dev_score) > 3.0 else "medium"
                    anomalies.append(AnomalyItem(
                        metric=metric,
                        dimension=f"slice:{name}",
                        period="2017-2018 (All-Time)",
                        observed=round(val, 2),
                        expected=round(float(median), 2),
                        deviation_score=dev_score,
                        severity=severity,
                        direction=direction,
                        method="iqr_dimension",
                        known_event_candidate=None
                    ))

        return anomalies

    @classmethod
    def detect_isolation_forest(
        cls,
        df: pd.DataFrame,
        contamination: float = 0.03,
        confirmed_periods: Optional[set] = None
    ) -> List[AnomalyItem]:
        """
        Method (d): Multivariate IsolationForest across daily vectors
        [gross_revenue, order_count, aov, on_time_delivery_rate].
        Requires agreement with at least one other method to elevate to medium/high severity;
        stand-alone IsolationForest outliers are marked 'low' so normal data does not falsely
        flag ~3% as medium/high anomalies.
        """
        if not SKLEARN_AVAILABLE or len(df) < 20:
            return []

        feature_cols = ["gross_revenue", "order_count", "aov", "on_time_delivery_rate"]
        X = df[feature_cols].copy().fillna(df[feature_cols].median())

        anomalies: List[AnomalyItem] = []
        try:
            iso = IsolationForest(contamination=contamination, random_state=42, n_estimators=100)
            preds = iso.fit_predict(X)
            scores = -iso.score_samples(X)  # higher = more anomalous

            median_rev = float(df["gross_revenue"].median())
            cold_cutoff = None
            period_dates = None
            date_col = "period_date" if "period_date" in df.columns else ("period" if "period" in df.columns else None)
            if date_col is not None and len(df) >= 90:
                try:
                    period_dates = pd.to_datetime(df[date_col])
                    cold_cutoff = period_dates.min() + pd.Timedelta(days=cls.COLD_START_DAYS)
                except Exception:
                    cold_cutoff = None
                    period_dates = None

            for i in range(len(df)):
                # Cold start filtering
                if cold_cutoff is not None and period_dates is not None and period_dates.iloc[i] < cold_cutoff:
                    continue

                if preds[i] == -1:  # Outlier detected
                    score = float(scores[i])
                    obs_rev = float(df["gross_revenue"].iloc[i])
                    period_str = str(df["period"].iloc[i])
                    event = format_known_event(period_str)
                    classification = event if event else "statistical_outlier"

                    direction = "spike" if obs_rev >= median_rev else "drop"

                    # Multi-method agreement check
                    is_confirmed = confirmed_periods is not None and period_str in confirmed_periods
                    if is_confirmed:
                        severity = "high" if score > 0.65 else "medium"
                    else:
                        severity = "low"

                    anomalies.append(AnomalyItem(
                        metric="multivariate_daily",
                        dimension="overall",
                        period=period_str,
                        observed=round(obs_rev, 2),
                        expected=round(median_rev, 2),
                        deviation_score=round(score, 3),
                        severity=severity,
                        direction=direction,
                        method="isolation_forest",
                        known_event_candidate=event,
                        classification=classification
                    ))
        except Exception as e:
            logger.debug(f"IsolationForest failed: {e}")

        return anomalies

    @classmethod
    def detect_all(
        cls,
        grain: str = "daily",
        metric: str = "gross_revenue",
        severity: Optional[str] = None,
        df: Optional[pd.DataFrame] = None,
        iqr_anomalies: Optional[List[AnomalyItem]] = None,
        dataset_id: str = "olist-demo"
    ) -> AnomalyListResponse:
        """
        Execute ensemble anomaly detection methods, format time series points,
        and filter results by metric, grain, and severity.
        Cache key is scoped by (dataset_id, grain, metric, severity) for multi-tenant isolation.
        Cold start excluded, small samples filtered, and dimension slice outliers separated.
        """
        cache_key = (dataset_id, grain, metric, severity)
        df_supplied = df is not None
        if df is None:
            now = time.time()
            with cls._cache_lock:
                if cache_key in cls._detect_cache:
                    cached_time, cached_res = cls._detect_cache[cache_key]
                    if now - cached_time < cls.CACHE_TTL:
                        return cached_res

            df = cls.get_time_series(grain=grain, dataset_id=dataset_id)

        if metric not in df.columns:
            target_metric = "gross_revenue"
        else:
            target_metric = metric

        # 1. Run detection algorithms
        zscore_anomalies = cls.detect_rolling_zscore(df, metric=target_metric, window=14, threshold=2.5)
        stl_anomalies = cls.detect_stl_residuals(df, metric=target_metric, period=7 if grain == "daily" else 4, threshold=2.5)
        if iqr_anomalies is None:
            iqr_anomalies = cls.detect_iqr_dimension_slices(metric=target_metric)

        # Collect periods flagged by z-score or STL
        confirmed_periods = {a.period for a in (zscore_anomalies + stl_anomalies)}
        iso_anomalies = cls.detect_isolation_forest(df, confirmed_periods=confirmed_periods) if grain == "daily" else []

        # Time-series items (excluding slice outliers)
        time_series_items = zscore_anomalies + stl_anomalies + iso_anomalies

        # Method agreement and max deviation mapping for severity calibration
        period_methods = defaultdict(set)
        period_max_dev = defaultdict(float)
        for a in time_series_items:
            period_methods[a.period].add(a.method)
            if abs(a.deviation_score) > abs(period_max_dev[a.period]):
                period_max_dev[a.period] = a.deviation_score

        # Calibrate severity and apply neutral labels
        calibrated_items: List[AnomalyItem] = []
        seen_keys = set()
        for item in time_series_items:
            key = (item.metric, item.dimension, item.period)
            if key not in seen_keys:
                seen_keys.add(key)
                m_count = len(period_methods[item.period])
                dev_mag = abs(period_max_dev[item.period])

                # Severity Calibration:
                # High severity: Multi-method agreement (>= 2 methods) AND deviation >= 8.0,
                # OR extreme deviation >= 12.0
                if (m_count >= 2 and dev_mag >= 8.0) or (dev_mag >= 12.0):
                    item.severity = "high"
                elif (m_count >= 2 and dev_mag >= 2.5) or (dev_mag >= 4.0):
                    item.severity = "medium"
                else:
                    item.severity = "low"

                if item.known_event_candidate:
                    item.classification = item.known_event_candidate
                else:
                    item.classification = "statistical_outlier"

                calibrated_items.append(item)

        # Label dimension slice outliers
        for s in iqr_anomalies:
            s.classification = "slice_outlier"

        # Filter by severity if specified
        filtered_items = calibrated_items
        if severity and severity.lower() in ("high", "medium", "low"):
            filtered_items = [a for a in calibrated_items if a.severity.lower() == severity.lower()]

        filtered_items.sort(key=lambda x: abs(x.deviation_score), reverse=True)

        # 2. Build time series points for frontend recharts
        time_series_points: List[AnomalyTimeSeriesPoint] = []
        anomaly_map = {a.period: a for a in filtered_items if a.dimension == "overall"}

        # Calculate smooth expected baseline (rolling 14-day median)
        series_vals = df[target_metric].astype(float)
        rolling_baseline = series_vals.rolling(window=14, min_periods=3, center=True).median().fillna(series_vals.median())

        for idx, row in df.iterrows():
            period_str = str(row["period"])
            obs_val = float(row[target_metric])
            exp_val = float(rolling_baseline.iloc[idx])
            matched_anom = anomaly_map.get(period_str)
            event_name = format_known_event(period_str)

            time_series_points.append(AnomalyTimeSeriesPoint(
                period=period_str,
                observed=round(obs_val, 2),
                expected=round(exp_val, 2),
                is_anomaly=bool(matched_anom is not None),
                severity=matched_anom.severity if matched_anom else None,
                direction=matched_anom.direction if matched_anom else None,
                known_event=event_name
            ))

        response = AnomalyListResponse(
            total_anomalies=len(filtered_items),
            grain=grain,
            metric=target_metric,
            anomalies=filtered_items,
            time_series=time_series_points,
            slice_outliers=iqr_anomalies
        )

        # Only cache results this call fetched itself. Callers that pass df/iqr_anomalies
        # (run_full_scan passes iqr_anomalies=[]) must not overwrite the page's cache entry,
        # and run_full_scan post-processes the returned items.
        if not df_supplied:
            with cls._cache_lock:
                cls._detect_cache[cache_key] = (time.time(), response)

        return response

    @classmethod
    def run_full_scan(cls, metrics: Optional[List[str]] = None, grain: str = "daily") -> AnomalyScanResponse:
        """
        Executes comprehensive multi-metric scan across business series.
        Fetches the time-series once and shares across all metrics.
        Calibrates severity, applies neutral labels, and separates slice outliers.
        """
        scan_id = str(uuid.uuid4())[:8]
        target_metrics = metrics or ["gross_revenue", "order_count", "aov", "on_time_delivery_rate", "avg_review_score"]
        all_detected: List[AnomalyItem] = []

        # Single shared database query for time series & dimension slices
        df = cls.get_time_series(grain=grain)
        iqr_slices = cls.detect_iqr_dimension_slices(metric="gross_revenue")

        for m in target_metrics:
            res = cls.detect_all(
                grain=grain,
                metric=m,
                df=df,
                iqr_anomalies=[]  # Don't mix slice outliers into metric time series
            )
            all_detected.extend(res.anomalies)

        # Multi-metric deduplication. Severity is kept exactly as detect_all calibrated it:
        # detect_all already returns one item per (metric, dimension, period), so re-counting
        # methods here would see a single method per period and wrongly downgrade
        # multi-method detections (e.g. 2018-05-16, dev 11.15: HIGH -> MEDIUM).
        seen = set()
        deduped = []
        for a in all_detected:
            k = (a.metric, a.dimension, a.period)
            if k not in seen:
                seen.add(k)

                if a.known_event_candidate:
                    a.classification = a.known_event_candidate
                else:
                    a.classification = "statistical_outlier"

                deduped.append(a)

        deduped.sort(key=lambda x: abs(x.deviation_score), reverse=True)
        high_sev = sum(1 for a in deduped if a.severity == "high")

        # Dimension slice outliers
        for s in iqr_slices:
            s.classification = "slice_outlier"

        return AnomalyScanResponse(
            scan_id=scan_id,
            status="completed",
            anomalies_detected=len(deduped),
            high_severity_count=high_sev,
            scanned_metrics=target_metrics,
            anomalies=deduped,
            slice_outliers=iqr_slices
        )
