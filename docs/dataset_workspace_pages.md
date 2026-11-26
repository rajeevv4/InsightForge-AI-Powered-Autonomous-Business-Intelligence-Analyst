# Dataset-Aware Workspace Pages

InsightForge has **one active dataset for the whole app**. Pick it in the header switcher (next to the page
title). With the built-in **Olist demo** selected, every page behaves exactly as before. With an **uploaded
dataset** selected, every sidebar page shows that dataset's data, computed deterministically (no AI).

## What works for uploaded datasets

| Page | Olist demo | Uploaded dataset | Backend endpoint (uploaded) |
|---|---|---|---|
| Header switcher | Shows "Olist demo" | Shows dataset name + expiry countdown | `GET /api/datasets` |
| Sidebar | Fixed 12 Olist items | Core items + one item per table + Geography / Payments / Delivery / Sellers only when matching columns exist | `GET /api/datasets/{id}/navigation` |
| Overview | Olist executive KPIs | KPI cards from semantic measures, monthly trend of the primary amount-like measure, up to 8 breakdowns with "all groups total" reconciliation | `GET /api/datasets/{id}/overview?limit=8` |
| Analytics | Olist analytics tabs | Metric picker (any measure or row count), daily / weekly / monthly trend, breakdowns | `GET /api/datasets/{id}/analytics?metric=&grain=&limit=` |
| Table pages (`/tables/:table`) | not applicable (redirects to Overview) | Row count, column profile, KPIs, trend, breakdowns of that table | `GET /api/datasets/{id}/tables/{table}/analysis` |
| Geography / Payments / Delivery / Sellers | Olist tabs | The table analysis filtered to the matching columns (e.g. revenue by city) | `GET /api/datasets/{id}/groups/{group}/analysis` |
| Customers / Products | Olist tabs | Explains these are Olist pages; use the table pages | none |
| Data Quality | Olist audit | Live checks: key uniqueness, FK orphans (confirmed relationships), negative values, future dates, missing values, join safety, status breakdown | `GET /api/datasets/{id}/data-quality` |
| Anomalies | Olist detection | Rolling MAD z-score, STL, IQR slices, IsolationForest (>= 3 measures), same severity calibration, known-event candidates | `GET /api/datasets/{id}/anomalies`, `POST /api/datasets/{id}/anomalies/scan` |
| Ask InsightForge | Olist Q&A | Dataset Q&A (Gemini Text-to-SQL), Quick Insights (now with working anomalies), Semantic Layer, Dashboard tab | existing endpoints |

## Safety model (identical for every new endpoint)

- **Owner isolation.** Every endpoint loads the dataset through `DatasetService.get_dataset_profile`, which
  rejects a wrong or missing `X-Owner-Token` with **403** (`detail` explains why) and an unknown id with **404**.
  The in-memory cache stores the hash of the owner token that produced each entry and never serves it to
  another token.
- **One query path.** Identifiers are quoted with sqlglot, every statement is validated by `SQLValidator` with a
  `DatasetSQLContext` (schema-qualified, allow-listed tables, single SELECT, row cap 500), then executed by the
  existing read-only path `DatasetInsightsService.execute_guarded_sql_in_schema` (`SET LOCAL ROLE dsr_<id>`,
  `search_path`, 5 s statement timeout). No new connection paths.
- **No fan-out.** A dimension from another table is used only along a **confirmed** relationship where the
  current table is the many side and the other table's key is unique per the profile (N:1), as a `LEFT JOIN`.
  Everything else is listed under "Skipped" with the reason (e.g. "relationship ... is not confirmed").
- **No LLM.** The semantic model is loaded with `allow_llm=False`, so even a first-time draft is deterministic.
- **Privacy.** Only aggregates and the owner's own group labels are returned, to the owner's browser. Nothing
  is sent to any model or written to logs. Text column ranges are never echoed on table pages.
- **Independent sections.** Each section is computed separately; a failure returns that section as `null` with
  a short reason in `section_errors` instead of failing the page.
- **No currency assumption.** Numbers are shown plain (thousands separators, averages to 2 decimals).

## Navigation rules

All topic keywords live in one documented constant, `NAV_GROUP_KEYWORDS`
(`backend/app/services/dataset_navigation_service.py`):

| Group | Shown when a column name matches |
|---|---|
| Geography | city, state, country, region, district, pincode, zip, location (semantic dimension names/synonyms and column names) |
| Payments | payment, method, mode, installment |
| Delivery | delivery, shipping, dispatch, lead_time |
| Sellers | seller, vendor, merchant, supplier |

Matching is on **whole name tokens** (plus `s`/`es` plurals), so `customer_city` matches *city* but `capacity`
does not, and `statement` does not match *state*.

## Anomaly detection details

- Detectors (a) MAD z-score, (b) STL and (c) IQR slices are the Olist functions called unchanged; (d)
  IsolationForest is a mirror of the Olist one (same contamination, `random_state=42`, cold start and severity
  rule) over the dataset's own measures. Calibration is the same as `AnomalyService.detect_all`; a unit test
  proves identical output on the Olist fixture series.
- Days without rows are counted as **zero** for SUM / COUNT measures (no activity is real), and left empty for
  averages.
- Averages (AVG / MIN / MAX) follow the Olist small-sample rule: periods with fewer than 30 rows are not tested.
- A series whose median absolute deviation is 0 (e.g. daily sign-ups that are mostly 0 or 1) is skipped with a
  note; use the weekly grain.
- Known events come from `GENERIC_EVENT_CATALOG` (Black Friday, Cyber Monday, Christmas, New Year), shown only as
  "(candidate)". Add entries there; they never change detection or severity.

## Caching

`WorkspaceCache` (in-memory, 10 minutes) keys on (page, dataset id, parameters). It is cleared for a dataset when
its relationships or column roles are patched, its semantic model is generated or patched, or it is deleted.

## Known limitations

- Query results are capped at 500 rows by the validator: daily trends longer than 500 days are labelled
  "(first 500 periods)" and anomaly detection notes it.
- The profiler labels a numeric column whose values are all unique as `id` (e.g. a small `amount` column); such a
  column is then not a semantic measure. Data-quality checks still treat fractional numeric columns as quantities.
- The 11 original dataset endpoints were converted from `async def` to `def` (blocking database work now runs in
  the threadpool, so a slow dataset request no longer stalls Olist requests).

## Tests

```bash
USE_FIXTURES=1 python -m unittest discover -s backend/tests      # offline suite (includes all workspace tests)
python scripts/diff_olist_snapshots.py --base http://127.0.0.1:8000   # Olist must be byte-for-byte unchanged
INSIGHTFORGE_API_BASE=http://127.0.0.1:8000 python -m unittest backend.tests_integration.test_olist_snapshots_live
```

Workspace test files: `test_dataset_navigation.py`, `test_dataset_workspace_pages.py`,
`test_dataset_workspace_tables.py`, `test_dataset_anomalies.py`, `test_dataset_workspace_isolation.py`.
