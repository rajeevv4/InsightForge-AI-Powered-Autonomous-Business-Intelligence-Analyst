import React, { useEffect, useState, useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  TrendingUp,
  ShoppingBag,
  MapPin,
  Store,
  CreditCard,
  Truck,
  Layers,
  Filter
} from 'lucide-react';
import { api } from '../services/api';
import {
  MonthlyTrendItem,
  CategoryItem,
  StateItem,
  SellerItem,
  DeliverySLAItem,
  PaymentItem
} from '../types/api';

import { RevenueTrendChart } from '../components/RevenueTrendChart';
import { CategoryChart } from '../components/CategoryChart';
import { StateChart } from '../components/StateChart';
import { SellerChart } from '../components/SellerChart';
import { PaymentChart } from '../components/PaymentChart';
import { DeliveryChart } from '../components/DeliveryChart';

type SectionTab = 'all' | 'revenue' | 'products' | 'geography' | 'sellers' | 'payments' | 'delivery';

export const AnalyticsPage: React.FC = () => {
  const outletContext = useOutletContext<{ refreshTrigger?: number }>();
  const [activeTab, setActiveTab] = useState<SectionTab>('all');

  const [revenueTrend, setRevenueTrend] = useState<MonthlyTrendItem[] | null>(null);
  const [categories, setCategories] = useState<CategoryItem[] | null>(null);
  const [states, setStates] = useState<StateItem[] | null>(null);
  const [sellers, setSellers] = useState<SellerItem[] | null>(null);
  const [deliverySLA, setDeliverySLA] = useState<DeliverySLAItem[] | null>(null);
  const [payments, setPayments] = useState<PaymentItem[] | null>(null);

  const [trendLoading, setTrendLoading] = useState<boolean>(true);
  const [trendError, setTrendError] = useState<string | null>(null);

  const [categoryLoading, setCategoryLoading] = useState<boolean>(true);
  const [categoryError, setCategoryError] = useState<string | null>(null);

  const [stateLoading, setStateLoading] = useState<boolean>(true);
  const [stateError, setStateError] = useState<string | null>(null);

  const [sellerLoading, setSellerLoading] = useState<boolean>(true);
  const [sellerError, setSellerError] = useState<string | null>(null);

  const [deliveryLoading, setDeliveryLoading] = useState<boolean>(true);
  const [deliveryError, setDeliveryError] = useState<string | null>(null);

  const [paymentLoading, setPaymentLoading] = useState<boolean>(true);
  const [paymentError, setPaymentError] = useState<string | null>(null);

  const loadAnalyticsData = useCallback(async () => {
    // 1. Revenue Trend
    setTrendLoading(true);
    setTrendError(null);
    api.getRevenueTrend()
      .then(setRevenueTrend)
      .catch(() => setTrendError('Failed to fetch revenue trend analytics'))
      .finally(() => setTrendLoading(false));

    // 2. Categories
    setCategoryLoading(true);
    setCategoryError(null);
    api.getCategories(10)
      .then(setCategories)
      .catch(() => setCategoryError('Failed to fetch product category analytics'))
      .finally(() => setCategoryLoading(false));

    // 3. States
    setStateLoading(true);
    setStateError(null);
    api.getStates()
      .then(setStates)
      .catch(() => setStateError('Failed to fetch customer state analytics'))
      .finally(() => setStateLoading(false));

    // 4. Sellers
    setSellerLoading(true);
    setSellerError(null);
    api.getSellers(10)
      .then(setSellers)
      .catch(() => setSellerError('Failed to fetch top sellers analytics'))
      .finally(() => setSellerLoading(false));

    // 5. Delivery SLA
    setDeliveryLoading(true);
    setDeliveryError(null);
    api.getDeliverySLA()
      .then(setDeliverySLA)
      .catch(() => setDeliveryError('Failed to fetch delivery performance'))
      .finally(() => setDeliveryLoading(false));

    // 6. Payments
    setPaymentLoading(true);
    setPaymentError(null);
    api.getPayments()
      .then(setPayments)
      .catch(() => setPaymentError('Failed to fetch payment method analytics'))
      .finally(() => setPaymentLoading(false));
  }, []);

  useEffect(() => {
    loadAnalyticsData();
  }, [loadAnalyticsData, outletContext?.refreshTrigger]);

  const tabs: { id: SectionTab; label: string; icon: React.FC<{ className?: string }> }[] = [
    { id: 'all', label: 'All Analytics', icon: Layers },
    { id: 'revenue', label: 'Revenue', icon: TrendingUp },
    { id: 'products', label: 'Products', icon: ShoppingBag },
    { id: 'geography', label: 'Geography', icon: MapPin },
    { id: 'sellers', label: 'Sellers', icon: Store },
    { id: 'payments', label: 'Payments', icon: CreditCard },
    { id: 'delivery', label: 'Delivery', icon: Truck },
  ];

  return (
    <div className="space-y-8 pb-12">
      {/* Page Heading */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight">Business Analytics</h1>
          <p className="text-xs text-slate-400 mt-1">
            Explore deep operational dimensions across revenue trends, merchandise categories, geography, merchant fulfillment, and payment methods.
          </p>
        </div>
      </div>

      {/* Category Section Filter Tabs */}
      <div className="flex items-center space-x-2 overflow-x-auto pb-2 scrollbar-none">
        <div className="flex items-center space-x-1 text-xs text-slate-400 mr-2 font-medium">
          <Filter className="w-3.5 h-3.5 text-cyan-400" />
          <span>Category Filter:</span>
        </div>
        {tabs.map((t) => {
          const Icon = t.icon;
          const isActive = activeTab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`flex items-center space-x-2 px-3.5 py-2 rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
                isActive
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                  : 'bg-slate-900/80 text-slate-400 hover:text-slate-200 border border-slate-800 hover:border-slate-700'
              }`}
            >
              <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-cyan-400' : 'text-slate-400'}`} />
              <span>{t.label}</span>
            </button>
          );
        })}
      </div>

      {/* Analytics Sections */}
      <div className="space-y-8">
        {/* SECTION 1 — Revenue */}
        {(activeTab === 'all' || activeTab === 'revenue') && (
          <section className="space-y-3">
            <div className="flex items-center space-x-2 text-sm font-bold text-white tracking-tight">
              <TrendingUp className="w-4 h-4 text-cyan-400" />
              <h2>SECTION 1 — Monthly Revenue Performance</h2>
            </div>
            <RevenueTrendChart
              data={revenueTrend}
              loading={trendLoading}
              error={trendError}
              onRetry={loadAnalyticsData}
            />
          </section>
        )}

        {/* SECTION 2 — Products */}
        {(activeTab === 'all' || activeTab === 'products') && (
          <section className="space-y-3">
            <div className="flex items-center space-x-2 text-sm font-bold text-white tracking-tight">
              <ShoppingBag className="w-4 h-4 text-emerald-400" />
              <h2>SECTION 2 — Top Product Categories</h2>
            </div>
            <CategoryChart
              data={categories}
              loading={categoryLoading}
              error={categoryError}
              onRetry={loadAnalyticsData}
            />
          </section>
        )}

        {/* SECTION 3 — Geography */}
        {(activeTab === 'all' || activeTab === 'geography') && (
          <section className="space-y-3">
            <div className="flex items-center space-x-2 text-sm font-bold text-white tracking-tight">
              <MapPin className="w-4 h-4 text-blue-400" />
              <h2>SECTION 3 — State Sales Distribution</h2>
            </div>
            <StateChart
              data={states}
              loading={stateLoading}
              error={stateError}
              onRetry={loadAnalyticsData}
            />
          </section>
        )}

        {/* SECTION 4 — Sellers */}
        {(activeTab === 'all' || activeTab === 'sellers') && (
          <section className="space-y-3">
            <div className="flex items-center space-x-2 text-sm font-bold text-white tracking-tight">
              <Store className="w-4 h-4 text-purple-400" />
              <h2>SECTION 4 — Top Seller Performance</h2>
            </div>
            <SellerChart
              data={sellers}
              loading={sellerLoading}
              error={sellerError}
              onRetry={loadAnalyticsData}
            />
          </section>
        )}

        {/* SECTION 5 — Payments */}
        {(activeTab === 'all' || activeTab === 'payments') && (
          <section className="space-y-3">
            <div className="flex items-center space-x-2 text-sm font-bold text-white tracking-tight">
              <CreditCard className="w-4 h-4 text-amber-400" />
              <h2>SECTION 5 — Payment Method Distribution</h2>
            </div>
            <PaymentChart
              data={payments}
              loading={paymentLoading}
              error={paymentError}
              onRetry={loadAnalyticsData}
            />
          </section>
        )}

        {/* SECTION 6 — Delivery */}
        {(activeTab === 'all' || activeTab === 'delivery') && (
          <section className="space-y-3">
            <div className="flex items-center space-x-2 text-sm font-bold text-white tracking-tight">
              <Truck className="w-4 h-4 text-indigo-400" />
              <h2>SECTION 6 — Delivery SLA Performance</h2>
            </div>
            <DeliveryChart
              data={deliverySLA}
              loading={deliveryLoading}
              error={deliveryError}
              onRetry={loadAnalyticsData}
            />
          </section>
        )}
      </div>
    </div>
  );
};
