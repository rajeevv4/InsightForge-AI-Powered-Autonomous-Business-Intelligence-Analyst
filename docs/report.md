# One-Click Report

Sidebar → **Report** (`/report`), or **Generate report** on Overview or right after an upload. It works for the
Olist demo and for uploaded datasets. Every number comes from the existing services, called directly in Python
(not over HTTP), so the values are identical to the other pages. All text is filled in from fixed templates. No LLM.

## Endpoints

| Source | Endpoint |
|---|---|
| Olist | `GET /api/report?format=json\|pdf` |
| Uploaded | `GET /api/datasets/{id}/report?format=json\|pdf` + `X-Owner-Token` |

- **Rate limit:** `RATE_LIMIT_REPORT` (default `10/hour` per client IP; JSON and PDF both count). A 429 response has a `detail` key.
- **PDF delivery:** streamed from memory as `InsightForge_Report_<dataset>_<date>.pdf`.

## Sections and their sources

| Section | Olist | Uploaded dataset |
|---|---|---|
| Header (period, row counts) | Data quality audit row counts and revenue-trend months | Stored profile and overview trend |
| Executive summary (5–8 sentences) | Templates over the sections below | same |
| KPI tiles | `AnalyticsService.fetch_canonical_kpis` (Overview) | `DatasetWorkspaceService.get_overview` (Overview) |
| Monthly trend | `fetch_revenue_trend` | `overview.trend` |
| Top breakdowns with an "All groups total" line | categories / states / payments | `overview.breakdowns` (first 4) |
| Top 5 anomalies with their driver sentence | `AnomalyService.detect_all` and Feature 1 | `DatasetAnomalyService` and Feature 1 |
| 3-month forecast (or its refusal) | Feature 2 | Feature 2 |
| Data quality (PASS / WARN / FAIL) | `DataQualityService.fetch_audit_summary` | `DatasetWorkspaceQuality.get_data_quality` |
| Caveats and methodology | Fixed text plus notes from the sections | same |

## How the report is built

- **Parallel, with a budget:** sections run in parallel (6 workers), with anomaly explanations limited to 2 at a time, all within a 45 s budget.
- **Failures are isolated:** a section that fails or runs out of time shows "Section unavailable: <reason>", with database timeouts reworded in plain language.
- **Short cache:** reports are cached for 120 s per dataset and owner, so the PDF download reuses the preview. Degraded reports are not cached.
- **Uploaded datasets:** the owner check runs before any cache lookup.

## PDF

- **Layout:** reportlab and matplotlib (Agg backend), A4, "Page x of y" footer, every table cell wrapped as a paragraph, headings kept with their first block.
- **Fonts:** the first Unicode TTF found is used (Arial Unicode on macOS, else Noto or DejaVu, with matplotlib's bundled DejaVu as the last resort). If none loads, it falls back to Helvetica and replaces unsupported characters with "?".
- **Text safety:** all text is XML-escaped before layout.
- **Known limitation:** reportlab does not shape complex scripts, so Devanagari conjuncts may appear unjoined (but never crash).
