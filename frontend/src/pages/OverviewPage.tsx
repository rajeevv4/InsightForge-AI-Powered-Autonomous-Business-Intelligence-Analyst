import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import {
  DollarSign,
  ShoppingBag,
  Users,
  PackageCheck,
  TrendingUp,
  Star,
  Layers,
  Truck,
  Sparkles,
  BarChart3,
  ShieldCheck,
  ArrowRight
} from 'lucide-react';
import { api } from '../services/api';
import {
  KPISummaryResponse,
  MonthlyTrendItem,
  CategoryItem,
  DeliverySLAItem
} from '../types/api';

import { KpiCard } from '../components/KpiCard';
import { RevenueTrendChart } from '../components/RevenueTrendChart';
import { CategoryChart } from '../components/CategoryChart';
import { DeliveryChart } from '../components/DeliveryChart';

export const OverviewPage: React.FC = () => {
  const navigate = useNavigate();
  const outletContext = useOutletContext<{ refreshTrigger?: number }>();

  const [kpis, setKpis] = useState<KPISummaryResponse | null>(null);
  const [revenueTrend, setRevenueTrend] = useState<MonthlyTrendItem[] | null>(null);
  const [categories, setCategories] = useState<CategoryItem[] | null>(null);
  const [deliverySLA, setDeliverySLA] = useState<DeliverySLAItem[] | null>(null);

  const [kpiLoading, setKpiLoading] = useState<boolean>(true);
  const [kpiError, setKpiError] = useState<string | null>(null);

  const [trendLoading, setTrendLoading] = useState<boolean>(true);
  const [trendError, setTrendError] = useState<string | null>(null);

  const [categoryLoading, setCategoryLoading] = useState<boolean>(true);
  const [categoryError, setCategoryError] = useState<string | null>(null);

  const [deliveryLoading, setDeliveryLoading] = useState<boolean>(true);
  const [deliveryError, setDeliveryError] = useState<string | null>(null);

  const loadOverviewData = useCallback(async () => {
    // 1. KPIs
    setKpiLoading(true);
    setKpiError(null);
    api.getKPIs()
      .then(setKpis)
      .catch(() => setKpiError('Failed to fetch executive KPIs'))
      .finally(() => setKpiLoading(false));

    // 2. Revenue Trend
    setTrendLoading(true);
    setTrendError(null);
    api.getRevenueTrend()
      .then(setRevenueTrend)
      .catch(() => setTrendError('Failed to fetch revenue trend analytics'))
      .finally(() => setTrendLoading(false));

    // 3. Categories
    setCategoryLoading(true);
    setCategoryError(null);
    api.getCategories(10)
      .then(setCategories)
      .catch(() => setCategoryError('Failed to fetch category analytics'))
      .finally(() => setCategoryLoading(false));

    // 4. Delivery SLA
    setDeliveryLoading(true);
    setDeliveryError(null);
    api.getDeliverySLA()
      .then(setDeliverySLA)
      .catch(() => setDeliveryError('Failed to fetch delivery performance'))
      .finally(() => setDeliveryLoading(false));
  }, []);

  useEffect(() => {
    loadOverviewData();
  }, [loadOverviewData, outletContext?.refreshTrigger]);

  const fmtCurr = (val: number | undefined) =>
    val !== undefined ? `R$ ${val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—';
  const fmtNum = (val: number | undefined) => (val !== undefined ? val.toLocaleString() : '—');

  return (
    <div className="space-y-8 pb-12">
      {/* Page Heading */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800/80 pb-4">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight">Executive Business Overview</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Key operational metrics, revenue performance, and logistics indicators for delivered orders.
          </p>
        </div>
        <span className="text-xs font-mono bg-slate-900 border border-slate-800 text-cyan-400 px-3 py-1 rounded-lg self-start sm:self-auto">
          Delivered Scope: 96,478 Orders
        </span>
      </div>

      {/* Executive KPI Cards Grid */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          title="Gross Revenue"
          value={fmtCurr(kpis?.gross_revenue)}
          subtitle="Product + Freight Sales"
          icon={DollarSign}
          color="blue"
        />
        <KpiCard
          title="Product Revenue"
          value={fmtCurr(kpis?.product_revenue)}
          subtitle="Net Merchandise Sales"
          icon={ShoppingBag}
          color="emerald"
        />
        <KpiCard
          title="Freight Revenue"
          value={fmtCurr(kpis?.freight_revenue)}
          subtitle="Shipping Charges Collected"
          icon={Truck}
          color="amber"
        />
        <KpiCard
          title="Delivered Orders"
          value={fmtNum(kpis?.delivered_orders)}
          subtitle="Fulfilled E-Commerce Orders"
          icon={PackageCheck}
          color="purple"
        />
        <KpiCard
          title="Active Customers"
          value={fmtNum(kpis?.active_customers)}
          subtitle="Unique Purchasing Customers"
          icon={Users}
          color="slate"
        />
        <KpiCard
          title="Units Sold"
          value={fmtNum(kpis?.units_sold)}
          subtitle="Total Purchased Line Items"
          icon={Layers}
          color="blue"
        />
        <KpiCard
          title="Average Order Value"
          value={fmtCurr(kpis?.aov)}
          subtitle="Revenue per Transaction"
          icon={TrendingUp}
          color="emerald"
        />
        <KpiCard
          title="Customer Rating (CSAT)"
          value={kpis?.csat ? `${kpis.csat.toFixed(2)} / 5.0` : '—'}
          subtitle="Mean Satisfaction Rating"
          icon={Star}
          color="amber"
        />
      </section>

      {/* High-Level Visualizations */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <RevenueTrendChart
          data={revenueTrend}
          loading={trendLoading}
          error={trendError}
          onRetry={loadOverviewData}
        />
        <CategoryChart
          data={categories}
          loading={categoryLoading}
          error={categoryError}
          onRetry={loadOverviewData}
        />
      </section>

      {/* Delivery SLA High-Level Chart */}
      <section>
        <DeliveryChart
          data={deliverySLA}
          loading={deliveryLoading}
          error={deliveryError}
          onRetry={loadOverviewData}
        />
      </section>

      {/* Feature Navigation Cards */}
      <section className="pt-4">
        <div className="text-sm font-semibold text-slate-400 mb-4 uppercase tracking-wider">
          Explore Deep Insights & Tools
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Ask AI Card */}
          <div className="bg-slate-900/90 border border-slate-800 hover:border-cyan-500/40 rounded-2xl p-6 transition-all group flex flex-col justify-between shadow-lg">
            <div>
              <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 mb-4 group-hover:scale-110 transition-transform">
                <Sparkles className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-white mb-1">Ask InsightForge AI</h3>
              <p className="text-xs text-slate-400 leading-relaxed mb-6">
                Ask business questions using natural language. Powered by Gemini 2.5 Flash grounded in PostgreSQL data.
              </p>
            </div>
            <button
              onClick={() => navigate('/ask')}
              className="flex items-center justify-between text-xs font-semibold text-cyan-400 hover:text-cyan-300 pt-3 border-t border-slate-800/80 group-hover:translate-x-1 transition-transform"
            >
              <span>Ask AI Question</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>

          {/* Business Analytics Card */}
          <div className="bg-slate-900/90 border border-slate-800 hover:border-blue-500/40 rounded-2xl p-6 transition-all group flex flex-col justify-between shadow-lg">
            <div>
              <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-400 mb-4 group-hover:scale-110 transition-transform">
                <BarChart3 className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-white mb-1">Business Analytics</h3>
              <p className="text-xs text-slate-400 leading-relaxed mb-6">
                Explore revenue trends, product categories, geographic state sales, top sellers, and payment breakdowns.
              </p>
            </div>
            <button
              onClick={() => navigate('/analytics')}
              className="flex items-center justify-between text-xs font-semibold text-blue-400 hover:text-blue-300 pt-3 border-t border-slate-800/80 group-hover:translate-x-1 transition-transform"
            >
              <span>Explore Analytics</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>

          {/* Data Quality Card */}
          <div className="bg-slate-900/90 border border-slate-800 hover:border-emerald-500/40 rounded-2xl p-6 transition-all group flex flex-col justify-between shadow-lg">
            <div>
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 mb-4 group-hover:scale-110 transition-transform">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-white mb-1">Data Quality & Audit</h3>
              <p className="text-xs text-slate-400 leading-relaxed mb-6">
                Inspect database integrity, audit status, null counts, foreign key validations, and join safety.
              </p>
            </div>
            <button
              onClick={() => navigate('/data-quality')}
              className="flex items-center justify-between text-xs font-semibold text-emerald-400 hover:text-emerald-300 pt-3 border-t border-slate-800/80 group-hover:translate-x-1 transition-transform"
            >
              <span>View Data Quality</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </section>
    </div>
  );
};
