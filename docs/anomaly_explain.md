# Explain This Anomaly (root-cause waterfall)

Every anomaly log row has an **Explain** button. It opens a drawer titled
"Why did <metric> <spike|drop> on <date>?". Entry points:

- the Olist Anomalies page
- the uploaded-dataset Anomalies page
- the Dashboard tab
- Quick Insights

Everything is deterministic. Numbers come from SQL aggregates, and sentences come from fixed templates in
`backend/app/services/anomaly_explain_service.py`. No Gemini call is made.

## Endpoints

| Source | Endpoint | Rate limit |
|---|---|---|
| Olist demo | `GET /api/anomalies/explain?metric=&period=&grain=` | `RATE_LIMIT_ANOMALY_EXPLAIN` (default = `RATE_LIMIT_AI_ASK`, 30/minute) |
| Uploaded dataset | `GET /api/datasets/{id}/anomalies/explain?period=&metric=&grain=` + `X-Owner-Token` | same |

A 429 response keeps slowapi's `error` key and adds a `detail` key.

## Method

- **Baseline:** the 14 periods before the anomaly (the same window the rolling z-score detector uses).
- **Queries:** one grouped query per dimension, using conditional aggregation for the target period and the baseline window. Queries run in parallel and results are cached for 10 minutes.
- **Additive metrics (SUM / COUNT):**
  - `expected_k = baseline_k / n * (E / Σ baseline_k / n)`, with `contribution_k = observed_k - expected_k`.
  - The waterfall runs from the detector's Expected value E to Observed and reconciles exactly.
  - Any gap between grouped totals and the headline goes into "All other".
- **Rates and averages:**
  - `contribution_k = N1_k / D1 - N0_k / D0`, which sums exactly to `R1 - R0`.
  - The waterfall starts at the trailing level ("Trailing avg").
- **Volume vs value (sum metrics):** volume effect `(V1 - V0) * A0` plus value effect `(A1 - A0) * V1` equals the change exactly.
  - Olist: V is orders, A is average order value.
  - Uploaded datasets: V is rows, A is the average per row.
- **Explanatory power:** the share of the change explained by a dimension's top 3 groups.
- **Mix shift:** the total variation distance between the baseline group mix and the anomaly-period mix. It compares the 10 largest groups plus an "other" bucket.
- **Tab order:** tabs are sorted by `explanatory_power x mix_shift`, best first.

## Fan-out rules

- **Olist:**
  - Delivered orders only, with the same filters as the anomaly series.
  - Item revenue and reviews are pre-aggregated to one row per order before joining.
  - The payment type is the primary one (`payment_sequential = 1`, part of the primary key).
  - Order counts and review scores are never split by item-level dimensions (category, seller). These are listed as skipped, with the reason.
- **Uploaded datasets:**
  - Dimensions come from `plan_breakdowns`, so joins only follow confirmed N:1 relationships.
  - Every statement passes `SQLValidator(DatasetSQLContext)` and runs through the scoped read-only path.
  - Date literals come from `date.isoformat()`.

Tests: `backend/tests/test_anomaly_explain.py` (25 tests).
