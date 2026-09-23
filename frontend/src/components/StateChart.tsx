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
    <div className="bg-white border border-slate-200/80 rounded-xl p-6 shadow-xs">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-base font-bold text-slate-900 tracking-tight">Regional Sales Performance</h2>
          <p className="text-xs text-slate-500 mt-0.5">Gross revenue concentration across top Brazilian customer states</p>
        </div>
      </div>

      <div className="h-[280px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={topStates} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
            <XAxis dataKey="state" stroke="#64748B" fontSize={11} tickLine={false} />
            <YAxis stroke="#64748B" fontSize={11} tickLine={false} tickFormatter={(v) => `₹${(v / 1000000).toFixed(1)}M`} />
            <Tooltip
              contentStyle={{
                backgroundColor: '#FFFFFF',
                borderColor: '#E2E8F0',
                borderRadius: '0.75rem',
                color: '#0F172A',
                boxShadow: '0 10px 15px -3px rgba(0,0,0,0.08)',
                fontSize: '12px'
              }}
              formatter={(val: any) => [`₹ ${Number(val).toLocaleString('en-US', { minimumFractionDigits: 2 })}`, 'Gross Revenue']}
            />
            <Bar dataKey="total_gross_revenue" fill="#2563EB" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
