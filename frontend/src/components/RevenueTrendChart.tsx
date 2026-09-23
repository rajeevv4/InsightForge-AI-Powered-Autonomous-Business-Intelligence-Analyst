import React from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid
} from 'recharts';
import { MonthlyTrendItem } from '../types/api';
import { LoadingSpinner } from './LoadingSpinner';
import { ErrorBanner } from './ErrorBanner';

interface RevenueTrendChartProps {
  data: MonthlyTrendItem[] | null;
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
}

export const RevenueTrendChart: React.FC<RevenueTrendChartProps> = ({
  data,
  loading,
  error,
  onRetry
}) => {
  if (loading) return <LoadingSpinner message="Loading monthly revenue trends..." />;
  if (error || !data) return <ErrorBanner message={error || 'Failed to load revenue trend'} onRetry={onRetry} />;

  const formattedData = data.map((d) => ({
    ...d,
    displayMonth: new Date(d.month).toLocaleDateString('en-US', { year: '2-digit', month: 'short' }),
    grossRevenueK: Math.round(d.gross_revenue / 1000),
  }));

  return (
    <div className="bg-white border border-slate-200/80 rounded-xl p-6 shadow-xs">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-base font-bold text-slate-900 tracking-tight">Revenue Trend</h2>
          <p className="text-xs text-slate-500 mt-0.5">Monthly gross sales revenue and fulfilled order volume</p>
        </div>
      </div>

      <div className="h-[320px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={formattedData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="revenueGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#4F46E5" stopOpacity={0.15} />
                <stop offset="95%" stopColor="#4F46E5" stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
            <XAxis dataKey="displayMonth" stroke="#64748B" fontSize={11} tickLine={false} />
            <YAxis
              yAxisId="left"
              stroke="#4F46E5"
              fontSize={11}
              tickLine={false}
              tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              stroke="#94A3B8"
              fontSize={11}
              tickLine={false}
              tickFormatter={(v) => `${(v / 1000).toFixed(1)}k`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#FFFFFF',
                borderColor: '#E2E8F0',
                borderRadius: '0.75rem',
                color: '#0F172A',
                boxShadow: '0 10px 15px -3px rgba(0,0,0,0.08), 0 4px 6px -2px rgba(0,0,0,0.05)',
                fontSize: '12px'
              }}
              formatter={(val: any, name: string) => {
                if (name === 'Gross Revenue') return [`₹${Number(val).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`, name];
                if (name === 'Delivered Orders') return [`${Number(val).toLocaleString()} orders`, name];
                return [val, name];
              }}
            />

            <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '12px' }} />
            <Bar yAxisId="right" dataKey="total_orders" name="Delivered Orders" fill="#CBD5E1" opacity={0.7} radius={[4, 4, 0, 0]} />
            <Area
              yAxisId="left"
              type="monotone"
              dataKey="gross_revenue"
              name="Gross Revenue"
              stroke="#4F46E5"
              strokeWidth={2.5}
              fillOpacity={1}
              fill="url(#revenueGrad)"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
