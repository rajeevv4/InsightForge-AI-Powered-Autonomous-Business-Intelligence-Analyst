import React from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  LabelList
} from 'recharts';
import { formatCompact, formatMoney } from '../lib/format';
import { TruncatedTick } from './ui';
import { CategoryItem } from '../types/api';
import { LoadingSpinner } from './LoadingSpinner';
import { ErrorBanner } from './ErrorBanner';

interface CategoryChartProps {
  data: CategoryItem[] | null;
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
}

export const CategoryChart: React.FC<CategoryChartProps> = ({
  data,
  loading,
  error,
  onRetry
}) => {
  if (loading) return <LoadingSpinner message="Loading product category sales..." />;
  if (error || !data) return <ErrorBanner message={error || 'Failed to load category analytics'} onRetry={onRetry} />;

  const formattedData = data.map((d) => ({
    ...d,
    formattedCategory: d.category.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase()),
  }));

  return (
    <div className="bg-white border border-slate-200/80 rounded-2xl p-4 sm:p-6 shadow-xs min-w-0 card-lift animate-fade-in-up">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-base font-bold text-slate-900 tracking-tight">Top Product Categories</h2>
          <p className="text-xs text-slate-500 mt-0.5">Revenue contribution and sales volume by merchandise category</p>
        </div>
      </div>

      <div className="w-full" style={{ height: Math.max(280, formattedData.length * 30) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={formattedData} layout="vertical" margin={{ top: 5, right: 56, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" horizontal={false} />
            <XAxis type="number" stroke="#64748B" fontSize={10} tickLine={false} tickFormatter={(v) => formatCompact(Number(v), 'R$')} />
            <YAxis dataKey="formattedCategory" type="category" stroke="#475569" width={112} tickLine={false} interval={0} tick={<TruncatedTick max={17} />} />
            <Tooltip
              contentStyle={{
                backgroundColor: '#FFFFFF',
                borderColor: '#E2E8F0',
                borderRadius: '0.75rem',
                color: '#0F172A',
                boxShadow: '0 10px 15px -3px rgba(0,0,0,0.08)',
                fontSize: '12px'
              }}
              formatter={(val: any) => [formatMoney(Number(val), 'R$'), 'Revenue']}
              cursor={{ fill: 'rgba(99,102,241,0.06)' }}
            />

            <Bar dataKey="total_revenue" fill="#4F46E5" radius={[0, 6, 6, 0]} animationDuration={800}>
              <LabelList dataKey="total_revenue" position="right" fontSize={10} fill="#475569" formatter={(v: any) => formatCompact(Number(v), 'R$')} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
