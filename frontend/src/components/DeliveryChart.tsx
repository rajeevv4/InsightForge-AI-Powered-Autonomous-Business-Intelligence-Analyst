import React from 'react';
import { Truck, Clock, AlertTriangle } from 'lucide-react';
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
    <div className="bg-slate-900/70 border border-slate-800/80 rounded-xl p-5 shadow-lg shadow-black/20">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight">Delivery SLA Performance</h2>
          <p className="text-xs text-slate-400">Order fulfillment timeliness and delivery SLA compliance</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        
        {/* On-Time Card */}
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider">On-Time</span>
            <Truck className="w-5 h-5 text-emerald-400" />
          </div>
          <div className="mt-3">
            <span className="text-2xl font-extrabold text-white font-mono">{onTime?.percentage.toFixed(2)}%</span>
            <p className="text-xs text-slate-300 mt-1">{onTime?.order_count.toLocaleString()} orders</p>
            <p className="text-[11px] text-emerald-400/80 mt-1">Avg {onTime?.avg_actual_delivery_days} days to door</p>
          </div>
        </div>

        {/* Delayed Card */}
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-amber-400 uppercase tracking-wider">Delayed</span>
            <Clock className="w-5 h-5 text-amber-400" />
          </div>
          <div className="mt-3">
            <span className="text-2xl font-extrabold text-white font-mono">{delayed?.percentage.toFixed(2)}%</span>
            <p className="text-xs text-slate-300 mt-1">{delayed?.order_count.toLocaleString()} orders</p>
            <p className="text-[11px] text-amber-400/80 mt-1">Avg {delayed?.avg_delay_days} days late</p>
          </div>
        </div>

        {/* Undelivered Card */}
        <div className="bg-rose-500/10 border border-rose-500/20 rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-rose-400 uppercase tracking-wider">Undelivered</span>
            <AlertTriangle className="w-5 h-5 text-rose-400" />
          </div>
          <div className="mt-3">
            <span className="text-2xl font-extrabold text-white font-mono">{undelivered?.percentage.toFixed(2)}%</span>
            <p className="text-xs text-slate-300 mt-1">{undelivered?.order_count.toLocaleString()} orders</p>
            <p className="text-[11px] text-rose-400/80 mt-1">Pending carrier resolution</p>
          </div>
        </div>

      </div>
    </div>
  );
};
