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
import { LabelList } from 'recharts';
import { formatCompact, formatMoney } from '../lib/format';
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
    <div className="bg-white border border-slate-200/80 rounded-2xl p-4 sm:p-6 shadow-xs min-w-0 card-lift animate-fade-in-up">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-base font-bold text-slate-900 tracking-tight">Regional Sales Performance</h2>
          <p className="text-xs text-slate-500 mt-0.5">Gross revenue concentration across top Brazilian customer states</p>
        </div>
      </div>

      <div className="h-[300px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={topStates} layout="vertical" margin={{ top: 4, right: 60, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" horizontal={false} />
            <XAxis type="number" stroke="#64748B" fontSize={10} tickLine={false} tickFormatter={(v) => formatCompact(Number(v), 'R$')} />
            <YAxis type="category" dataKey="state" stroke="#475569" fontSize={11} width={36} tickLine={false} interval={0} />
            <Tooltip
              contentStyle={{
                backgroundColor: '#FFFFFF',
                borderColor: '#E2E8F0',
                borderRadius: '0.75rem',
                color: '#0F172A',
                boxShadow: '0 10px 15px -3px rgba(0,0,0,0.08)',
                fontSize: '12px'
              }}
              formatter={(val: any) => [formatMoney(Number(val), 'R$'), 'Gross Revenue']}
              cursor={{ fill: 'rgba(37,99,235,0.06)' }}
            />
            <Bar dataKey="total_gross_revenue" fill="#2563EB" radius={[0, 6, 6, 0]} animationDuration={800}>
              <LabelList dataKey="total_gross_revenue" position="right" fontSize={10} fill="#475569" formatter={(v: any) => formatCompact(Number(v), 'R$')} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
