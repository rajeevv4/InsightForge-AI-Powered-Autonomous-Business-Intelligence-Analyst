import React from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid
} from 'recharts';
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
    <div className="bg-slate-900/70 border border-slate-800/80 rounded-xl p-5 shadow-lg shadow-black/20">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight">Top Product Categories</h2>
          <p className="text-xs text-slate-400">Revenue contribution % and unit sales by English category</p>
        </div>
      </div>

      <div className="h-[280px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={formattedData} layout="vertical" margin={{ top: 5, right: 20, left: 40, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" horizontal={false} />
            <XAxis type="number" stroke="#64748B" fontSize={11} tickFormatter={(v) => `R$${(v / 1000).toFixed(0)}k`} />
            <YAxis dataKey="formattedCategory" type="category" stroke="#94A3B8" fontSize={11} width={110} tickLine={false} />
            <Tooltip
              contentStyle={{ backgroundColor: '#0F172A', borderColor: '#334155', borderRadius: '0.5rem', color: '#F8FAFC', fontSize: '12px' }}
              formatter={(val: any) => [`R$ ${Number(val).toLocaleString('en-US', { minimumFractionDigits: 2 })}`, 'Revenue']}
            />
            <Bar dataKey="total_revenue" fill="#0ea5e9" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
