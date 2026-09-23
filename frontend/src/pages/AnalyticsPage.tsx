import React, { useEffect, useState, useCallback } from 'react';
import { useOutletContext, useLocation } from 'react-router-dom';
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

interface AnalyticsPageProps {
  initialTab?: SectionTab;
}

export const AnalyticsPage: React.FC<AnalyticsPageProps> = ({ initialTab }) => {
  const location = useLocation();
  const outletContext = useOutletContext<{ refreshTrigger?: number }>();

  const getInitialTab = (): SectionTab => {
    if (initialTab) return initialTab;
    const searchParams = new URLSearchParams(location.search);
    const tabParam = searchParams.get('tab') as SectionTab;
    if (tabParam && ['all', 'revenue', 'products', 'geography', 'sellers', 'payments', 'delivery'].includes(tabParam)) {
      return tabParam;
    }
    // Handle path matching if loaded as alias
    if (location.pathname === '/products') return 'products';
    if (location.pathname === '/geography' || location.pathname === '/customers') return 'geography';
    if (location.pathname === '/sellers') return 'sellers';
    if (location.pathname === '/payments') return 'payments';
    if (location.pathname === '/delivery') return 'delivery';

    return 'all';
  };

  const [activeTab, setActiveTab] = useState<SectionTab>(getInitialTab());

  useEffect(() => {
    setActiveTab(getInitialTab());
  }, [location.pathname, location.search]);

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
    { id: 'all', label: 'All Sections', icon: Layers },
    { id: 'revenue', label: 'Revenue Trends', icon: TrendingUp },
    { id: 'products', label: 'Products & Categories', icon: ShoppingBag },
    { id: 'geography', label: 'Geography & Customers', icon: MapPin },
    { id: 'sellers', label: 'Sellers', icon: Store },
    { id: 'payments', label: 'Payments', icon: CreditCard },
    { id: 'delivery', label: 'Delivery SLA', icon: Truck },
  ];

  return (
    <div className="space-y-8 pb-12">
      {/* Page Heading */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200/80 pb-4">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Business Analytics Workspace</h1>
          <p className="text-xs text-slate-500 mt-1">
            Detailed performance breakdown across revenue trends, merchandise categories, geographic customer states, merchants, and logistics.
          </p>
        </div>
      </div>

      {/* Segmented Filter Navigation Tabs */}
      <div className="flex items-center space-x-2 overflow-x-auto pb-2 scrollbar-none">
        <div className="flex items-center space-x-1 text-xs text-slate-500 mr-2 font-semibold">
          <Filter className="w-3.5 h-3.5 text-indigo-600" />
          <span>View Section:</span>
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
                  ? 'bg-indigo-600 text-white shadow-xs'
                  : 'bg-white text-slate-600 hover:text-slate-900 border border-slate-200/80 hover:border-slate-300'
              }`}
            >
              <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-white' : 'text-slate-400'}`} />
              <span>{t.label}</span>
            </button>
          );
        })}
      </div>

      {/* Categorized Sections */}
      <div className="space-y-8">
        {/* Revenue Section */}
        {(activeTab === 'all' || activeTab === 'revenue') && (
          <section className="space-y-3">
            <div className="border-b border-slate-200/60 pb-2">
              <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-indigo-600" />
                Revenue & Sales Trends
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Monthly gross revenue performance, order volume growth, and average order value trends.
              </p>
            </div>
            <RevenueTrendChart
              data={revenueTrend}
              loading={trendLoading}
              error={trendError}
              onRetry={loadAnalyticsData}
            />
          </section>
        )}

        {/* Products Section */}
        {(activeTab === 'all' || activeTab === 'products') && (
          <section className="space-y-3">
            <div className="border-b border-slate-200/60 pb-2">
              <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                <ShoppingBag className="w-4 h-4 text-emerald-600" />
                Products & Category Breakdown
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Top product categories ranked by revenue contribution percentage and item quantity sold.
              </p>
            </div>
            <CategoryChart
              data={categories}
              loading={categoryLoading}
              error={categoryError}
              onRetry={loadAnalyticsData}
            />
          </section>
        )}

        {/* Geography Section */}
        {(activeTab === 'all' || activeTab === 'geography') && (
          <section className="space-y-3">
            <div className="border-b border-slate-200/60 pb-2">
              <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                <MapPin className="w-4 h-4 text-blue-600" />
                Geographic Sales Distribution
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                State-level sales volume, active purchasing customer density, and freight revenue distribution.
              </p>
            </div>
            <StateChart
              data={states}
              loading={stateLoading}
              error={stateError}
              onRetry={loadAnalyticsData}
            />
          </section>
        )}

        {/* Sellers Section */}
        {(activeTab === 'all' || activeTab === 'sellers') && (
          <section className="space-y-3">
            <div className="border-b border-slate-200/60 pb-2">
              <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                <Store className="w-4 h-4 text-purple-600" />
                Seller & Merchant Performance
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Merchant order fulfillment volume, catalog assortment size, sales revenue, and customer ratings.
              </p>
            </div>
            <SellerChart
              data={sellers}
              loading={sellerLoading}
              error={sellerError}
              onRetry={loadAnalyticsData}
            />
          </section>
        )}

        {/* Payments Section */}
        {(activeTab === 'all' || activeTab === 'payments') && (
          <section className="space-y-3">
            <div className="border-b border-slate-200/60 pb-2">
              <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                <CreditCard className="w-4 h-4 text-amber-600" />
                Payment Method Breakdown
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Distribution of credit card, boleto, voucher, and debit payment values and installment plans.
              </p>
            </div>
            <PaymentChart
              data={payments}
              loading={paymentLoading}
              error={paymentError}
              onRetry={loadAnalyticsData}
            />
          </section>
        )}

        {/* Delivery Section */}
        {(activeTab === 'all' || activeTab === 'delivery') && (
          <section className="space-y-3">
            <div className="border-b border-slate-200/60 pb-2">
              <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                <Truck className="w-4 h-4 text-indigo-600" />
                Delivery SLA Performance
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Logistics timeliness, on-time vs delayed shipment rates, and carrier delivery day averages.
              </p>
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
