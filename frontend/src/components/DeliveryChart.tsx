import React from 'react';
import { Truck, Clock, AlertCircle } from 'lucide-react';
import { DeliverySLAItem } from '../types/api';
import { LoadingSpinner } from './LoadingSpinner';
import { ErrorBanner } from './ErrorBanner';

interface DeliveryChartProps {
  data: DeliverySLAItem[] | null;
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
}

export const DeliveryChart: React.FC<DeliveryChartProps> = ({
  data,
  loading,
  error,
  onRetry
}) => {
  if (loading) return <LoadingSpinner message="Loading delivery SLA performance..." />;
  if (error || !data) return <ErrorBanner message={error || 'Failed to load delivery SLA'} onRetry={onRetry} />;

  const onTime = data.find((d) => d.delivery_status === 'On-Time');
  const delayed = data.find((d) => d.delivery_status === 'Delayed');
  const undelivered = data.find((d) => d.delivery_status === 'Undelivered');

  return (
    <div className="bg-white border border-slate-200/80 rounded-xl p-6 shadow-xs">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-base font-bold text-slate-900 tracking-tight">Delivery SLA Performance</h2>
          <p className="text-xs text-slate-500 mt-0.5">Fulfillment SLA compliance and carrier delivery timelines</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* On-Time Card */}
        <div className="bg-emerald-50/80 border border-emerald-200/60 rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-emerald-700 uppercase tracking-wider">On-Time Deliveries</span>
            <Truck className="w-4 h-4 text-emerald-600" />
          </div>
          <div className="mt-4">
            <span className="text-2xl font-extrabold text-slate-900">{onTime?.percentage.toFixed(1)}%</span>
            <p className="text-xs text-slate-600 mt-1 font-medium">{onTime?.order_count.toLocaleString()} orders</p>
            <p className="text-[11px] text-emerald-700 mt-1">Avg {onTime?.avg_actual_delivery_days?.toFixed(1)} days delivery time</p>
          </div>
        </div>

        {/* Delayed Card */}
        <div className="bg-amber-50/80 border border-amber-200/60 rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-amber-700 uppercase tracking-wider">Delayed Deliveries</span>
            <Clock className="w-4 h-4 text-amber-600" />
          </div>
          <div className="mt-4">
            <span className="text-2xl font-extrabold text-slate-900">{delayed?.percentage.toFixed(1)}%</span>
            <p className="text-xs text-slate-600 mt-1 font-medium">{delayed?.order_count.toLocaleString()} orders</p>
            <p className="text-[11px] text-amber-700 mt-1">Avg {delayed?.avg_delay_days?.toFixed(1)} days delay</p>
          </div>
        </div>

        {/* Undelivered Card */}
        <div className="bg-rose-50/80 border border-rose-200/60 rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-rose-700 uppercase tracking-wider">Pending / Undelivered</span>
            <AlertCircle className="w-4 h-4 text-rose-600" />
          </div>
          <div className="mt-4">
            <span className="text-2xl font-extrabold text-slate-900">{undelivered?.percentage.toFixed(1)}%</span>
            <p className="text-xs text-slate-600 mt-1 font-medium">{undelivered?.order_count.toLocaleString()} orders</p>
            <p className="text-[11px] text-rose-700 mt-1">Pending carrier fulfillment</p>
          </div>
        </div>
      </div>
    </div>
  );
};
