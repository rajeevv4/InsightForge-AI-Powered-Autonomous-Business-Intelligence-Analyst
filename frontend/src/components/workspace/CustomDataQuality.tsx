import React, { useState } from 'react';
import { CheckCircle2, AlertTriangle, XCircle, MinusCircle, ShieldCheck } from 'lucide-react';
import { api } from '../../services/api';
import { useActiveDataset } from '../../contexts/ActiveDatasetContext';
import { DataQualityCheck } from '../../types/api';
import { ChartSkeleton, ErrorBanner, KpiSkeleton, PageHeader, fmtNumber, useWorkspaceData } from './shared';

const STATUS_STYLE: Record<string, { cls: string; icon: React.ReactNode }> = {
  PASS: { cls: 'bg-emerald-50 text-emerald-800 border-emerald-200', icon: <CheckCircle2 className="w-4 h-4 text-emerald-600" /> },
  WARN: { cls: 'bg-amber-50 text-amber-800 border-amber-200', icon: <AlertTriangle className="w-4 h-4 text-amber-600" /> },
  FAIL: { cls: 'bg-rose-50 text-rose-800 border-rose-200', icon: <XCircle className="w-4 h-4 text-rose-600" /> },
  SKIPPED: { cls: 'bg-slate-50 text-slate-600 border-slate-200', icon: <MinusCircle className="w-4 h-4 text-slate-400" /> },
};
const statusOf = (summary: string): string => (summary.split(' ')[0] || 'SKIPPED').toUpperCase();

const CHECK_LABEL: Record<string, string> = {
  primary_key: 'Primary key',
  foreign_key: 'Foreign key',
  negative_values: 'Negative values',
  future_dates: 'Future dates',
  missing_values: 'Missing values',
  join_safety: 'Join safety',
  table_scan: 'Table scan',
};

const SummaryCard: React.FC<{ title: string; summary: string }> = ({ title, summary }) => {
  const st = STATUS_STYLE[statusOf(summary)] || STATUS_STYLE.SKIPPED;
  return (
    <div className={`border rounded-2xl p-4 shadow-xs ${st.cls}`}>
      <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider">
        {st.icon}
        {title}
      </div>
      <div className="text-xs font-semibold mt-2">{summary || 'not run'}</div>
    </div>
  );
};

/** Data Quality for an uploaded dataset: live deterministic checks. */
export const CustomDataQuality: React.FC = () => {
  const { activeDatasetId, activeDataset } = useActiveDataset();
  const [showPassing, setShowPassing] = useState(false);
  const { data, loading, error, reload } = useWorkspaceData(
    `dq:${activeDatasetId}`,
    () => api.getDatasetDataQuality(activeDatasetId),
    'data quality checks'
  );
  const checks: DataQualityCheck[] = data?.checks || [];
  const visible = showPassing ? checks : checks.filter((c) => c.status !== 'PASS');
  const audit = STATUS_STYLE[(data?.audit_status || 'SKIPPED').toUpperCase()] || STATUS_STYLE.SKIPPED;

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        icon={<ShieldCheck className="w-4 h-4 text-indigo-600" />}
        title={`Data Quality: ${activeDataset?.name || 'Uploaded dataset'}`}
        subtitle="Live, deterministic checks: key uniqueness, orphans on confirmed relationships, negative values, future dates, missing values, join safety."
        loading={loading}
        cached={data?.cached}
        onRefresh={reload}
      />
      {error && <ErrorBanner message={error} />}
      {!data && loading && (
        <>
          <KpiSkeleton count={5} />
          <ChartSkeleton height="h-48" />
        </>
      )}

      {data && (
        <>
          <div className={`flex items-center gap-3 border rounded-2xl p-4 shadow-xs ${audit.cls}`}>
            {audit.icon}
            <div>
              <div className="text-sm font-bold">Audit status: {data.audit_status}</div>
              <div className="text-xs">
                {data.anomalies_flagged.length === 0
                  ? 'No problems found.'
                  : `${data.anomalies_flagged.length} issue${data.anomalies_flagged.length === 1 ? '' : 's'} flagged below.`}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            <SummaryCard title="Primary key uniqueness" summary={data.primary_key_uniqueness} />
            <SummaryCard title="Foreign key integrity" summary={data.foreign_key_integrity} />
            <SummaryCard title="Domain bounds" summary={data.domain_bounds_status} />
            <SummaryCard title="Join safety" summary={data.join_safety_status} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            <section className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
              <div className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-3">Table row counts</div>
              {Object.entries(data.table_row_counts).map(([t, n]) => (
                <div key={t} className="flex justify-between text-xs py-1 border-b border-slate-100">
                  <span className="font-mono">{t}</span>
                  <span className="font-semibold">{fmtNumber(n)}</span>
                </div>
              ))}
            </section>
            <section className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
              <div className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-3">Missing values</div>
              {Object.keys(data.missing_value_summary).length === 0 ? (
                <div className="text-xs text-emerald-700">No missing values.</div>
              ) : (
                Object.entries(data.missing_value_summary).map(([c, n]) => (
                  <div key={c} className="flex justify-between text-xs py-1 border-b border-slate-100">
                    <span className="font-mono">{c}</span>
                    <span className="font-semibold text-amber-700">{fmtNumber(n)}</span>
                  </div>
                ))
              )}
            </section>
            <section className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
              <div className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-3">
                Status breakdown {data.status_column ? <span className="font-mono normal-case">({data.status_column})</span> : ''}
              </div>
              {Object.keys(data.order_status_breakdown).length === 0 ? (
                <div className="text-xs text-slate-400">No status-like column in this dataset.</div>
              ) : (
                Object.entries(data.order_status_breakdown).map(([k, n]) => (
                  <div key={k} className="flex justify-between text-xs py-1 border-b border-slate-100">
                    <span>{k}</span>
                    <span className="font-semibold">{fmtNumber(n)}</span>
                  </div>
                ))
              )}
            </section>
          </div>

          <section className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
            <div className="flex items-center justify-between mb-3">
              <div className="text-xs font-bold uppercase tracking-wider text-slate-700">
                Checks ({checks.length} run, {checks.filter((c) => c.status !== 'PASS').length} not passing)
              </div>
              <label className="text-xs text-slate-600 flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" checked={showPassing} onChange={(e) => setShowPassing(e.target.checked)} />
                Show passing checks
              </label>
            </div>
            {visible.length === 0 ? (
              <div className="text-xs text-emerald-700">Every check passed.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-[10px] text-slate-500 uppercase tracking-wider border-b border-slate-200">
                    <tr>
                      <th className="py-2 pr-3">Status</th>
                      <th className="py-2 pr-3">Check</th>
                      <th className="py-2 pr-3">Column</th>
                      <th className="py-2">Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((c, i) => (
                      <tr key={i} className="border-b border-slate-100">
                        <td className="py-1.5 pr-3">
                          <span className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold ${STATUS_STYLE[c.status]?.cls || ''}`}>{c.status}</span>
                        </td>
                        <td className="py-1.5 pr-3">{CHECK_LABEL[c.check] || c.check}</td>
                        <td className="py-1.5 pr-3 font-mono text-[10px]">{c.table}{c.column ? `.${c.column}` : ''}</td>
                        <td className="py-1.5 text-slate-600">{c.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
};
