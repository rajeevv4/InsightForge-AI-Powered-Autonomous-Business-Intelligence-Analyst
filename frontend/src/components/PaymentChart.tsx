import React from 'react';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend
} from 'recharts';
import { PaymentItem } from '../types/api';
import { LoadingSpinner } from './LoadingSpinner';
import { ErrorBanner } from './ErrorBanner';

interface PaymentChartProps {
  data: PaymentItem[] | null;
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
}

const COLORS = ['#38BDF8', '#818CF8', '#F59E0B', '#34D399'];

export const PaymentChart: React.FC<PaymentChartProps> = ({
  data,
  loading,
  error,
  onRetry
}) => {
  if (loading) return <LoadingSpinner message="Loading payment distribution..." />;
  if (error || !data) return <ErrorBanner message={error || 'Failed to load payment analytics'} onRetry={onRetry} />;

  const formattedData = data.map((d) => ({
    name: d.payment_type.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase()),
    value: d.total_payment_value,
    count: d.order_count,
    installments: d.avg_installments
  }));

  return (
    <div className="bg-slate-900/70 border border-slate-800/80 rounded-xl p-5 shadow-lg shadow-black/20">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight">Payment Method Distribution</h2>
          <p className="text-xs text-slate-400">Gross transaction values and average installment plans</p>
        </div>
      </div>

      <div className="h-[280px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={formattedData}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={95}
              paddingAngle={4}
              dataKey="value"
            >
              {formattedData.map((_, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} stroke="#0F172A" strokeWidth={2} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{ backgroundColor: '#0F172A', borderColor: '#334155', borderRadius: '0.5rem', color: '#F8FAFC', fontSize: '12px' }}
              formatter={(val: any) => [`R$ ${Number(val).toLocaleString('en-US', { minimumFractionDigits: 2 })}`, 'Total Value']}
            />
            <Legend wrapperStyle={{ fontSize: '12px' }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
