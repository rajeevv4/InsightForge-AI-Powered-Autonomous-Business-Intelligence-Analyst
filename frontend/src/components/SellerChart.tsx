import React from 'react';
import { SellerItem } from '../types/api';
import { LoadingSpinner } from './LoadingSpinner';
import { ErrorBanner } from './ErrorBanner';

interface SellerChartProps {
  data: SellerItem[] | null;
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
}

export const SellerChart: React.FC<SellerChartProps> = ({
  data,
  loading,
  error,
  onRetry
}) => {
  if (loading) return <LoadingSpinner message="Loading merchant performance..." />;
  if (error || !data) return <ErrorBanner message={error || 'Failed to load seller analytics'} onRetry={onRetry} />;

  return (
    <div className="bg-white border border-slate-200/80 rounded-xl p-6 shadow-xs">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-base font-bold text-slate-900 tracking-tight">Top Sellers & Merchants</h2>
          <p className="text-xs text-slate-500 mt-0.5">Top performing merchants ranked by total sales revenue and fulfillment volume</p>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider">
              <th className="pb-3 px-2">Merchant ID</th>
              <th className="pb-3 px-2">Location</th>
              <th className="pb-3 px-2 text-right">Units</th>
              <th className="pb-3 px-2 text-right">Products</th>
              <th className="pb-3 px-2 text-right">Total Revenue</th>
              <th className="pb-3 px-2 text-right">CSAT</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.slice(0, 10).map((seller) => (
              <tr key={seller.seller_id} className="hover:bg-slate-50 transition">
                <td className="py-3 px-2 font-mono font-medium text-indigo-600">
                  {seller.seller_id.substring(0, 8)}...
                </td>
                <td className="py-3 px-2 text-slate-700">
                  {seller.seller_city}, {seller.seller_state}
                </td>
                <td className="py-3 px-2 text-right text-slate-800">
                  {seller.units_sold.toLocaleString()}
                </td>
                <td className="py-3 px-2 text-right text-slate-600">
                  {seller.unique_products_offered}
                </td>
                <td className="py-3 px-2 text-right font-bold text-slate-900">
                  ₹ {seller.total_sales_revenue.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </td>
                <td className="py-3 px-2 text-right text-amber-600 font-medium">
                  {seller.avg_seller_review_score ? `${seller.avg_seller_review_score.toFixed(2)} ★` : 'N/A'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
