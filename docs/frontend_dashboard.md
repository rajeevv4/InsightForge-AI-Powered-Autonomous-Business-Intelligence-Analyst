# InsightForge — React BI Dashboard Documentation

This document provides the architecture, component structure, design system specs, and API integration details for the **InsightForge React BI Dashboard**.

- **URL**: `http://localhost:3000`
- **Stack**: React 18, Vite 5, TypeScript 5, Tailwind CSS 3, Recharts 2, Axios 1, Lucide React icons
- **Target Backend API**: `http://localhost:8000/api`

---

## 📌 Dashboard Architecture & Components

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │                              HEADER COMPONENT                          │
 │  Title • Subtitle • Live Health Status (● Connected) • Refresh Button  │
 └────────────────────────────────────────────────────────────────────────┘
                                     │
 ┌───────────────────────────────────┴────────────────────────────────────┐
 │                      EXECUTIVE KPI CARDS GRID                          │
 │  Gross Rev • Product Rev • Freight Rev • Delivered Orders • Customers  │
 │  Units Sold • Average Order Value (AOV) • Customer Rating (CSAT)       │
 └────────────────────────────────────────────────────────────────────────┘
                                     │
 ┌───────────────────────────────────┴────────────────────────────────────┐
 │                     BI ANALYTICS & CHARTS GRID                         │
 │  1. Monthly Revenue Performance (Line/Area + Order Volume Bar)          │
 │  2. Top Product Categories (Horizontal Bar Chart)                      │
 │  3. Regional Sales Performance (State Distribution Bar Chart)          │
 │  4. Top Sellers (Merchant Volume & Sales Ranking Table)               │
 │  5. Delivery SLA Performance (On-Time / Delayed / Undelivered Cards)    │
 │  6. Payment Method Distribution (Donut Chart)                          │
 └────────────────────────────────────────────────────────────────────────┘
                                     │
 ┌───────────────────────────────────┴────────────────────────────────────┐
 │                      DATA QUALITY MONITOR PANEL                        │
 │  10-Check Audit Summary • PK/FK Integrity • Fan-Out Protection Status │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Component Directory Breakdown

- [`src/components/Header.tsx`](file:///Users/rajeev/Major%20Project-%20InsightForge/frontend/src/components/Header.tsx): Top navigation header displaying the title, live backend connection indicator (`● Connected`), and global **Refresh Data** button.
- [`src/components/KpiCard.tsx`](file:///Users/rajeev/Major%20Project-%20InsightForge/frontend/src/components/KpiCard.tsx): Reusable KPI card formatting currency in `R$`, numbers with commas, AOV with 2 decimal places, and CSAT ratings.
- [`src/components/RevenueTrendChart.tsx`](file:///Users/rajeev/Major%20Project-%20InsightForge/frontend/src/components/RevenueTrendChart.tsx): Recharts composed area/line chart overlaying monthly revenue and order volume.
- [`src/components/CategoryChart.tsx`](file:///Users/rajeev/Major%20Project-%20InsightForge/frontend/src/components/CategoryChart.tsx): Horizontal bar chart displaying top product categories and revenue contribution %.
- [`src/components/StateChart.tsx`](file:///Users/rajeev/Major%20Project-%20InsightForge/frontend/src/components/StateChart.tsx): Bar chart illustrating sales distribution across Brazilian states (`SP`, `RJ`, `MG`, etc.).
- [`src/components/SellerChart.tsx`](file:///Users/rajeev/Major%20Project-%20InsightForge/frontend/src/components/SellerChart.tsx): Table ranking top 10 merchants by sales revenue and unit volume.
- [`src/components/PaymentChart.tsx`](file:///Users/rajeev/Major%20Project-%20InsightForge/frontend/src/components/PaymentChart.tsx): Donut chart representing payment method distribution (`credit_card`, `boleto`, `voucher`, `debit_card`).
- [`src/components/DeliveryChart.tsx`](file:///Users/rajeev/Major%20Project-%20InsightForge/frontend/src/components/DeliveryChart.tsx): Fulfillment SLA status cards for `On-Time` (91.88%), `Delayed` (8.11%), and `Undelivered` (0.01%) orders.
- [`src/components/DataQualityCard.tsx`](file:///Users/rajeev/Major%20Project-%20InsightForge/frontend/src/components/DataQualityCard.tsx): Data quality audit status panel displaying 100% PASS metrics.
- [`src/services/api.ts`](file:///Users/rajeev/Major%20Project-%20InsightForge/frontend/src/services/api.ts): Centralized Axios service with configurable `VITE_API_BASE_URL` and `http://127.0.0.1:8000/api` fallback.

---

## 📸 Visual Verification Screenshot

![InsightForge BI Dashboard Visual Verification](/Users/rajeev/.gemini/antigravity-ide/brain/4d278606-25fb-43a8-84e7-83381c666557/dashboard_verification_1788628900479.png)

---

## 🛠️ How to Run

1. **Start FastAPI Backend Server** (Port 8000):
   ```bash
   python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
   ```
2. **Start React Frontend Dev Server** (Port 3000):
   ```bash
   cd frontend
   npm install
   npm run dev -- --port 3000
   ```
3. Open `http://localhost:3000` in browser.
