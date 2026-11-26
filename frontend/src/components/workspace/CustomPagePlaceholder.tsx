import React from 'react';
import { Link, useParams } from 'react-router-dom';
import { Construction, Info, LayoutDashboard } from 'lucide-react';
import { useActiveDataset } from '../../contexts/ActiveDatasetContext';

/**
 * Phase 1 placeholder shown for uploaded datasets on pages whose dataset-aware
 * version arrives in a later phase. Olist pages are never replaced by this.
 */

const PAGE_INFO: Record<string, { title: string; next: string }> = {
  overview: { title: 'Overview', next: 'KPI cards from your measures, monthly trend and top breakdowns.' },
  analytics: { title: 'Analytics', next: 'Metric picker, daily/weekly/monthly trend and breakdowns for every suitable column.' },
  table: { title: 'Table', next: 'Row count, column profile and breakdowns of this table.' },
  geography: { title: 'Geography', next: 'Breakdowns by your location columns (city, state, region...).' },
  sellers: { title: 'Sellers', next: 'Breakdowns by your seller / vendor columns.' },
  payments: { title: 'Payments', next: 'Breakdowns by your payment method / mode columns.' },
  delivery: { title: 'Delivery', next: 'Delivery and shipping metrics from your delivery columns.' },
  data_quality: { title: 'Data Quality', next: 'Real checks: key uniqueness, orphans, negative values, future dates, missing values, join safety.' },
  anomalies: { title: 'Anomalies', next: 'Rolling MAD, STL, IQR slice and IsolationForest outliers on your time series.' },
};

export const CustomPagePlaceholder: React.FC<{ page: string; olistOnly?: boolean }> = ({ page, olistOnly }) => {
  const { activeDataset } = useActiveDataset();
  const { tableName } = useParams();
  const info = PAGE_INFO[page] || { title: page, next: '' };
  const title = page === 'table' && tableName ? `Table: ${tableName}` : info.title;
  const datasetName = activeDataset?.name || 'your uploaded dataset';

  if (olistOnly) {
    return (
      <div className="bg-white border border-slate-200/80 rounded-2xl p-8 shadow-xs max-w-2xl">
        <div className="flex items-center gap-2 text-slate-700 font-bold text-sm mb-2">
          <Info className="w-4 h-4 text-indigo-600" />
          {info.title} is an Olist demo page
        </div>
        <p className="text-xs text-slate-600 leading-relaxed">
          You are viewing <span className="font-semibold">{datasetName}</span>. Use the table pages in the sidebar
          (one per table of your dataset), or switch back to the Olist demo in the header.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-200/80 rounded-2xl p-8 shadow-xs max-w-2xl">
      <div className="flex items-center gap-2 text-slate-900 font-bold text-sm mb-1">
        <Construction className="w-4 h-4 text-amber-600" />
        {title}: coming in the next phase
      </div>
      <p className="text-xs text-slate-500 mb-4">
        Dataset: <span className="font-semibold text-slate-700">{datasetName}</span>
      </p>
      {info.next && <p className="text-xs text-slate-600 leading-relaxed mb-5">This page will show: {info.next}</p>}
      <Link
        to="/ask"
        className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold"
      >
        <LayoutDashboard className="w-3.5 h-3.5" />
        Open the Dashboard tab in Ask InsightForge
      </Link>
    </div>
  );
};
