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

  // Filter valid dataset & format months
  const formattedData = data.map((d) => ({
    ...d,
    displayMonth: new Date(d.month).toLocaleDateString('en-US', { year: '2-digit', month: 'short' }),
    grossRevenueK: Math.round(d.gross_revenue / 1000),
  }));

  return (
    <div className="bg-slate-900/70 border border-slate-800/80 rounded-xl p-5 shadow-lg shadow-black/20">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight">Monthly Revenue Performance</h2>
          <p className="text-xs text-slate-400">Gross revenue trends and order volume with MoM growth rates</p>
        </div>
      </div>

      <div className="h-[320px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={formattedData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="revenueGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#38BDF8" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#38BDF8" stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
            <XAxis dataKey="displayMonth" stroke="#64748B" fontSize={11} tickLine={false} />
            <YAxis
              yAxisId="left"
              stroke="#38BDF8"
              fontSize={11}
              tickLine={false}
              tickFormatter={(v) => `R$${(v / 1000).toFixed(0)}k`}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              stroke="#818CF8"
              fontSize={11}
              tickLine={false}
              tickFormatter={(v) => `${(v / 1000).toFixed(1)}k`}
            />
            <Tooltip
              contentStyle={{ backgroundColor: '#0F172A', borderColor: '#334155', borderRadius: '0.5rem', color: '#F8FAFC', fontSize: '12px' }}
              formatter={(val: any, name: string) => {
                if (name === 'Gross Revenue') return [`R$ ${Number(val).toLocaleString('en-US', { minimumFractionDigits: 2 })}`, name];
                if (name === 'Delivered Orders') return [`${Number(val).toLocaleString()} orders`, name];
                return [val, name];
              }}
            />
            <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }} />
            <Bar yAxisId="right" dataKey="total_orders" name="Delivered Orders" fill="#6366F1" opacity={0.6} radius={[4, 4, 0, 0]} />
            <Area
              yAxisId="left"
              type="monotone"
              dataKey="gross_revenue"
              name="Gross Revenue"
              stroke="#38BDF8"
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
