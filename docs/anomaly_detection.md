# InsightForge Deterministic Anomaly Detection Engine

## 1. Overview
InsightForge Level 2 introduces a deterministic, multi-method anomaly detection framework for Brazilian e-commerce business analytics.

In accordance with Core Principle 4, **the LLM never detects anomalies or generates numbers**. All statistical anomalies and outliers are computed purely by deterministic Python algorithms operating over PostgreSQL delivered order data (with canonical fixture fallback under `USE_FIXTURES=1`). The LLM is restricted to synthesizing grounded explanations over computed anomaly evidence.

---

## 2. Core Metrics & Time Series
Time series are constructed from delivered orders (`order_status = 'delivered'`) at daily and weekly grains across five core metrics:
1. **Gross Revenue (`gross_revenue`)**: Product item price plus freight value for delivered orders.
2. **Delivered Orders (`order_count`)**: Unique delivered order count.
3. **Average Order Value (`aov`)**: Gross revenue divided by delivered order count.
4. **On-Time Delivery Rate (`on_time_delivery_rate`)**: Percentage of orders delivered on or before the estimated delivery SLA date.
5. **Customer Review Score (`avg_review_score`)**: Average review score rating (1.0 to 5.0).

> [!NOTE]
> Sparse early data (< `2017-01-01`) and incomplete final records (> `2018-08-31`) are trimmed to eliminate boundary artifacts.

---

## 3. Detection Algorithms

### (a) Rolling Robust Z-Score (Median / MAD)
- Standard z-score uses the mean and standard deviation, which are sensitive to the very outliers being detected.
- InsightForge implements the **Median Absolute Deviation (MAD)** robust z-score:
  $$\text{Modified } Z = 0.6745 \times \frac{x - \text{median}}{\text{MAD}}$$
  $$\text{where } \text{MAD} = \text{median}(|x - \text{median}|)$$
- Applied over a rolling sliding window (default: 7 periods).
- Severity classification:
  - **High**: $|\text{score}| \ge 5.0$
  - **Medium**: $3.5 \le |\text{score}| < 5.0$
  - **Low**: $2.5 \le |\text{score}| < 3.5$

### (b) STL Decomposition Residual Outliers
- Uses `statsmodels.tsa.seasonal.STL` (Seasonal and Trend decomposition using Loess).
- Isolates seasonality and trend to compute residuals:
  $$Y_t = T_t + S_t + R_t \implies R_t = Y_t - T_t - S_t$$
- Anomaly scoring is performed on the residual series $R_t$, ensuring recurring seasonal peaks (e.g. weekly shopping cycles) are not flagged as anomalous.

### (c) Interquartile Range (IQR) on Dimension Slices
- Detects concentration outliers across categorical dimensions (Customer State, Product Category, Seller performance):
  $$\text{IQR} = Q_3 - Q_1$$
  $$\text{Upper Fence} = Q_3 + (1.5 \times \text{IQR}), \quad \text{Lower Fence} = Q_1 - (1.5 \times \text{IQR})$$
- Points outside $[ \text{Lower Fence}, \text{Upper Fence} ]$ are flagged as slice outliers (e.g. SP state dominating revenue).

### (d) Isolation Forest (Multivariate Anomaly Detection)
- Implemented with `scikit-learn.ensemble.IsolationForest`.
- Builds an ensemble of isolation trees on multivariate daily vectors:
  $$[\text{gross\_revenue}, \text{order\_count}, \text{aov}, \text{on\_time\_delivery\_rate}]$$
- Detects compound multidimensional anomalies that may appear normal when inspecting individual univariate metrics.

---

## 4. Known Events Catalog
Seasonal retail surges should be tagged as expected promotional events rather than system errors. The engine cross-references detected anomaly dates against a known events catalog:
- **Black Friday 2017**: `2017-11-24` (gross revenue spiked to $R\$ 176,940.50$, over $6\times$ the daily average)
- **Cyber Monday 2017**: `2017-11-27`
- **Christmas Shopping Rush 2017**: `2017-12-15` through `2017-12-22`
- **Mother's Day Shopping Peak**: `2018-05-06` through `2018-05-13`
- **Valentine's Day (Dia dos Namorados)**: `2018-06-05` through `2018-06-12`

When an anomaly period coincides with these dates, `known_event_candidate` is populated and displayed in the UI and AI synthesis.

---

## 5. API Endpoints
- **`GET /api/anomalies?metric=gross_revenue&grain=daily&severity=all`**:
  - Returns `metric`, `grain`, `total_anomalies`, list of detected `AnomalyItem`s, and full `time_series` points with anomaly flags for charting.
  - Returns HTTP 503 if PostgreSQL is disconnected and `USE_FIXTURES != 1`.
- **`POST /api/anomalies/scan`**:
  - Runs full multi-metric anomaly scan.
  - Rate limited to `10/minute` via SlowAPI.
  - Telemetry logged to `AIAuditService`.

---

## 6. Frontend UI
- Accessible via the **Anomalies** link in the navigation sidebar (`/anomalies`).
- Visualized using Recharts with dual-line display (Observed vs Baseline) and colored anomaly highlight dots.
- Interactive controls for metric selection, grain toggle (`daily` / `weekly`), and severity filters.
- Displays comprehensive anomalies log table with $R\$$ currency formatting and `ErrorBanner` on 503 disconnected states.
