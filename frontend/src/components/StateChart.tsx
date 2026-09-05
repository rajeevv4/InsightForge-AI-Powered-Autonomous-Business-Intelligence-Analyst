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
import { StateItem } from '../types/api';
import { LoadingSpinner } from './LoadingSpinner';
import { ErrorBanner } from './ErrorBanner';

interface StateChartProps {
  data: StateItem[] | null;
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
}

export const StateChart: React.FC<StateChartProps> = ({
  data,
  loading,
  error,
  onRetry
}) => {
  if (loading) return <LoadingSpinner message="Loading regional state sales..." />;
  if (error || !data) return <ErrorBanner message={error || 'Failed to load state analytics'} onRetry={onRetry} />;

  const topStates = data.slice(0, 10);

  return (
    <div className="bg-slate-900/70 border border-slate-800/80 rounded-xl p-5 shadow-lg shadow-black/20">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight">Regional Sales Performance</h2>
          <p className="text-xs text-slate-400">Gross revenue and customer concentration across Brazilian states</p>
        </div>
      </div>

      <div className="h-[280px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={topStates} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
            <XAxis dataKey="state" stroke="#64748B" fontSize={11} tickLine={false} />
            <YAxis stroke="#64748B" fontSize={11} tickLine={false} tickFormatter={(v) => `R$${(v / 1000000).toFixed(1)}M`} />
            <Tooltip
              contentStyle={{ backgroundColor: '#0F172A', borderColor: '#334155', borderRadius: '0.5rem', color: '#F8FAFC', fontSize: '12px' }}
              formatter={(val: any) => [`R$ ${Number(val).toLocaleString('en-US', { minimumFractionDigits: 2 })}`, 'Gross Revenue']}
            />
            <Bar dataKey="total_gross_revenue" fill="#10b981" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
