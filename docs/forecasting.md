# Baseline Forecast

Sidebar → **Forecast** (`/forecast`), for the Olist demo and for uploaded datasets (uses the active dataset).
Deterministic: statsmodels ETS with fixed settings and a fixed simulation seed. All text is templated. No LLM.

> Baseline forecast: ignores promotions, price changes and one-off events.

## Endpoints

| Source | Endpoint | Rate limit |
|---|---|---|
| Olist | `GET /api/forecast?metric=gross_revenue\|order_count&horizon=1..6&exclude_anomalies=` | `RATE_LIMIT_FORECAST` (default = `RATE_LIMIT_AI_ASK`) |
| Uploaded | `GET /api/datasets/{id}/forecast?metric=table.column&horizon=&exclude_anomalies=` + `X-Owner-Token` | same |

Only SUM and COUNT measures can be forecast (monthly totals must add up). Results are cached for 10 minutes.
For uploaded datasets the cache is cleared when the semantic model or relationships change.

## Method

All thresholds are in `FORECAST_RULES` (`backend/app/services/forecast_service.py`).

1. **Monthly series.** Missing months count as 0.
   - A partial last month (data ends before the month's last day) is dropped.
   - Sparse leading months are dropped: history starts at the first 3 consecutive months that are at least 5% of the median month.
   - Every trim is listed under the chart.
2. **Model choice.**
   - At least 12 clean months: a **monthly model**.
   - Otherwise, at least 90 days: a **daily model**. It forecasts days, then sums 1,000 simulated paths (seed 42) to monthly totals and bands.
   - Otherwise the forecast is refused.
3. **ETSModel.**
   - Additive error and additive damped trend. The damping factor is bounded to 0.8–0.9, so a baseline doesn't extrapolate growth far.
   - Seasonality is used only with at least 2 full seasons (24 months, or 14 days for the weekly cycle).
   - 80% and 95% prediction intervals; every bound is at least 0.
4. **Backtest.** The model is refit without the last 3 months and compared with a naive baseline that repeats the last month. For the daily model, the holdout is the last 28 days, scored on 4 weekly totals against the same weekday of the last training week.
5. **Refusals.** No forecast numbers are shown when:
   - MAPE is above 40% and the model doesn't beat naive;
   - MAPE is above 100% (on noise, "beating naive" means nothing);
   - the first month's 80% band is wider than ±35% of the expected value (the model itself says the series is mostly noise);
   - there is no time column, too little data, or only zeros.

   Otherwise reliability is **Good** (MAPE ≤ 10%), **Fair** (≤ 25%) or **Weak**.
6. **Exclude flagged anomaly days** (optional). Each day flagged by the rolling z-score or STL detector on the overall series is replaced by the detector's expected value before training. The adjusted months show their original value in the history.

## Data paths

- **Olist:**
  - The existing monthly view behind `/api/analytics/revenue-trend` (delivered orders, same definitions as the KPIs).
  - One indexed `MAX(order_purchase_timestamp)` lookup.
  - With these, the partial August 2018 and the sparse 2016 months are trimmed, and training covers 2017-01 to 2018-07.
- **Uploaded datasets:**
  - Owner check (403 with `detail`).
  - One sqlglot-quoted monthly query, validated by `SQLValidator(DatasetSQLContext)` and run through the scoped read-only path.
  - The daily frame (only for the daily model) and the anomaly days come from `DatasetAnomalyService`, which uses the same path.

## Tests

`backend/tests/test_forecast.py` covers:
- a clear trend scoring Good;
- pure noise being refused (at least 9 of 10 seeds);
- short series being refused;
- the daily model;
- trimming;
- band ordering;
- repeated calls returning identical results;
- anomaly exclusion;
- owner isolation and the 403 / 400 / 422 responses;
- refusal (rather than a 500) when there is no time column;
- the rate-limit decorators.
