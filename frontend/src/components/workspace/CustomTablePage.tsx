import React from 'react';
import { useParams } from 'react-router-dom';
import { CreditCard, MapPin, Store, Table2, Truck } from 'lucide-react';
import { api } from '../../services/api';
import { useActiveDataset } from '../../contexts/ActiveDatasetContext';
import { WorkspaceTableAnalysisResponse } from '../../types/api';
import {
  BreakdownGrid,
  ChartSkeleton,
  ErrorBanner,
  KpiGrid,
  KpiSkeleton,
  PageHeader,
  TrendCard,
  Unavailable,
  fmtNumber,
  useWorkspaceData,
} from './shared';

const GROUP_META: Record<string, { title: string; icon: React.ReactNode }> = {
  geography: { title: 'Geography', icon: <MapPin className="w-4 h-4 text-indigo-600" /> },
  sellers: { title: 'Sellers', icon: <Store className="w-4 h-4 text-indigo-600" /> },
  payments: { title: 'Payments', icon: <CreditCard className="w-4 h-4 text-indigo-600" /> },
  delivery: { title: 'Delivery', icon: <Truck className="w-4 h-4 text-indigo-600" /> },
};

const ColumnsTable: React.FC<{ data: WorkspaceTableAnalysisResponse }> = ({ data }) => (
  <section className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
    <div className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-3">
      Columns {data.group ? '(matched for this page)' : `(${data.columns.length})`}
    </div>
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-[10px] text-slate-500 uppercase tracking-wider border-b border-slate-200">
          <tr>
            <th className="py-2 pr-3">Column</th>
            <th className="py-2 pr-3">Type</th>
            <th className="py-2 pr-3">Role</th>
            <th className="py-2 pr-3 text-right">Null %</th>
            <th className="py-2 pr-3 text-right">Distinct</th>
            <th className="py-2">Range</th>
          </tr>
        </thead>
        <tbody>
          {data.columns.map((c) => (
            <tr key={c.name} className="border-b border-slate-100">
              <td className="py-1.5 pr-3 font-mono font-semibold text-slate-800">{c.name}</td>
              <td className="py-1.5 pr-3 text-slate-500">{c.pg_type}</td>
              <td className="py-1.5 pr-3 text-slate-500">{c.role}</td>
              <td className={`py-1.5 pr-3 text-right ${c.null_pct > 0 ? 'text-amber-700' : 'text-slate-500'}`}>{c.null_pct.toFixed(1)}%</td>
              <td className="py-1.5 pr-3 text-right text-slate-500">{fmtNumber(c.distinct_count)}</td>
              <td className="py-1.5 text-slate-500 font-mono text-[10px]">{c.min_val !== null ? `${c.min_val} … ${c.max_val}` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </section>
);

const AnalysisView: React.FC<{ data: WorkspaceTableAnalysisResponse }> = ({ data }) => {
  const errs = data.section_errors || {};
  return (
    <>
      {data.group && data.matched_columns.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-slate-600">
          <span className="font-semibold">Columns used:</span>
          {data.matched_columns.map((c) => (
            <span key={c} className="px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 font-mono">{c}</span>
          ))}
        </div>
      )}
      <section>
        <div className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-2.5">Key Metrics</div>
        {data.kpis && data.kpis.length > 0 ? (
          <KpiGrid kpis={data.kpis} />
        ) : (
          <div className="bg-white border border-slate-200/80 rounded-2xl shadow-xs">
            <Unavailable reason={errs.kpis || 'no measures'} />
          </div>
        )}
      </section>
      <TrendCard trend={data.trend} reason={errs.trend} label="Monthly Trend" />
      <BreakdownGrid breakdowns={data.breakdowns} reason={errs.breakdowns} skipped={data.skipped_breakdowns} />
      {data.columns.length > 0 && <ColumnsTable data={data} />}
    </>
  );
};

const Loading: React.FC = () => (
  <>
    <KpiSkeleton count={4} />
    <ChartSkeleton />
  </>
);

/** /tables/:tableName for an uploaded dataset. */
export const CustomTablePage: React.FC = () => {
  const { tableName = '' } = useParams();
  const { activeDatasetId, activeDataset } = useActiveDataset();
  const { data, loading, error, reload } = useWorkspaceData(
    `table:${activeDatasetId}:${tableName}`,
    () => api.getDatasetTableAnalysis(activeDatasetId, tableName),
    `table ${tableName}`
  );
  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        icon={<Table2 className="w-4 h-4 text-indigo-600" />}
        title={`Table: ${tableName}`}
        subtitle={`${activeDataset?.name || 'Uploaded dataset'}${data ? ` · ${fmtNumber(data.row_count)} rows · ${data.columns.length} columns` : ''}`}
        loading={loading}
        cached={data?.cached}
        onRefresh={reload}
      />
      {error && <ErrorBanner message={error} />}
      {!data && loading && <Loading />}
      {data && <AnalysisView data={data} />}
    </div>
  );
};

/** Geography / Sellers / Payments / Delivery for an uploaded dataset (group view of the table analysis). */
export const CustomGroupPage: React.FC<{ group: 'geography' | 'sellers' | 'payments' | 'delivery' }> = ({ group }) => {
  const { activeDatasetId, activeDataset } = useActiveDataset();
  const meta = GROUP_META[group];
  const { data, loading, error, reload } = useWorkspaceData(
    `group:${activeDatasetId}:${group}`,
    () => api.getDatasetGroupAnalysis(activeDatasetId, group),
    meta.title.toLowerCase()
  );
  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        icon={meta.icon}
        title={`${meta.title}: ${activeDataset?.name || 'Uploaded dataset'}`}
        subtitle="Breakdowns by this dataset's matching columns. Joins only along confirmed N:1 relationships."
        loading={loading}
        cached={data?.cached}
        onRefresh={reload}
      />
      {error && <ErrorBanner message={error} />}
      {!data && loading && <Loading />}
      {data && <AnalysisView data={data} />}
    </div>
  );
};
