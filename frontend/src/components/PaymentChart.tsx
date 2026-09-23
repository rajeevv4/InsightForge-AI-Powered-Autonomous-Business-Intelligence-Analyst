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

const COLORS = ['#4F46E5', '#0284C7', '#D97706', '#059669'];

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
    <div className="bg-white border border-slate-200/80 rounded-xl p-6 shadow-xs">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-base font-bold text-slate-900 tracking-tight">Payment Method Distribution</h2>
          <p className="text-xs text-slate-500 mt-0.5">Gross transaction values and installment breakdown</p>
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
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} stroke="#FFFFFF" strokeWidth={2} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                backgroundColor: '#FFFFFF',
                borderColor: '#E2E8F0',
                borderRadius: '0.75rem',
                color: '#0F172A',
                boxShadow: '0 10px 15px -3px rgba(0,0,0,0.08)',
                fontSize: '12px'
              }}
              formatter={(val: any) => [`₹ ${Number(val).toLocaleString('en-US', { minimumFractionDigits: 2 })}`, 'Total Value']}
            />
            <Legend wrapperStyle={{ fontSize: '12px' }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
