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
    <div className="bg-slate-900/70 border border-slate-800/80 rounded-xl p-5 shadow-lg shadow-black/20">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight">Top Sellers</h2>
          <p className="text-xs text-slate-400">Top 10 merchants ranked by total sales revenue and fulfillment volume</p>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400 font-medium uppercase tracking-wider">
              <th className="pb-3 px-2">Merchant ID</th>
              <th className="pb-3 px-2">Location</th>
              <th className="pb-3 px-2 text-right">Units</th>
              <th className="pb-3 px-2 text-right">Products</th>
              <th className="pb-3 px-2 text-right">Total Revenue</th>
              <th className="pb-3 px-2 text-right">CSAT</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-mono">
            {data.slice(0, 10).map((seller) => (
              <tr key={seller.seller_id} className="hover:bg-slate-800/40 transition">
                <td className="py-2.5 px-2 font-medium text-sky-400">
                  {seller.seller_id.substring(0, 8)}...
                </td>
                <td className="py-2.5 px-2 text-slate-300 font-sans">
                  {seller.seller_city}, {seller.seller_state}
                </td>
                <td className="py-2.5 px-2 text-right text-slate-200">
                  {seller.units_sold.toLocaleString()}
                </td>
                <td className="py-2.5 px-2 text-right text-slate-300">
                  {seller.unique_products_offered}
                </td>
                <td className="py-2.5 px-2 text-right font-bold text-emerald-400">
                  R$ {seller.total_sales_revenue.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </td>
                <td className="py-2.5 px-2 text-right text-amber-400">
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
