import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { LayoutDashboard, ShieldCheck } from 'lucide-react';
import { api } from '../../services/api';
import { useActiveDataset } from '../../contexts/ActiveDatasetContext';
import {
  BreakdownGrid,
  ChartSkeleton,
  ErrorBanner,
  KpiGrid,
  KpiSkeleton,
  PageHeader,
  TrendCard,
  Unavailable,
  useWorkspaceData,
} from './shared';

/** Overview for an uploaded dataset (the Olist Overview page is untouched and used for the demo). */
export const CustomOverview: React.FC = () => {
  const { activeDatasetId, activeDataset } = useActiveDataset();
  const { data, loading, error, reload } = useWorkspaceData(
    `overview:${activeDatasetId}`,
    () => api.getDatasetOverview(activeDatasetId),
    'the overview'
  );
  const errs = data?.section_errors || {};
  const q = data?.quality_summary;

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        icon={<LayoutDashboard className="w-4 h-4 text-indigo-600" />}
        title={`Overview: ${activeDataset?.name || 'Uploaded dataset'}`}
        subtitle="Deterministic KPIs, monthly trend and breakdowns computed from your dataset. No AI involved."
        loading={loading}
        cached={data?.cached}
        onRefresh={reload}
      >
        <GenerateReportButton />
      </PageHeader>
      {error && <ErrorBanner message={error} />}

      {!data && loading && (
        <>
          <KpiSkeleton count={8} />
          <ChartSkeleton />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            <ChartSkeleton height="h-56" label=" " />
            <ChartSkeleton height="h-56" label=" " />
            <ChartSkeleton height="h-56" label=" " />
          </div>
        </>
      )}

      {data && (
        <>
          <section>
            <div className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-2.5">Key Metrics</div>
            {data.kpis && data.kpis.length > 0 ? (
              <KpiGrid kpis={data.kpis} />
            ) : (
              <div className="bg-white border border-slate-200/80 rounded-2xl shadow-xs">
                <Unavailable reason={errs.kpis || 'no measures found'} />
              </div>
            )}
          </section>

          <TrendCard trend={data.trend} reason={errs.trend} label="Monthly Trend" />

          <BreakdownGrid breakdowns={data.breakdowns} reason={errs.breakdowns} skipped={data.skipped_breakdowns} />

          <section className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs text-slate-700">
              <ShieldCheck className="w-4 h-4 text-indigo-600" />
              {q ? (
                <span>
                  Profiling found <span className="font-semibold">{q.findings}</span> data quality finding{q.findings === 1 ? '' : 's'} across {q.tables} table{q.tables === 1 ? '' : 's'}
                  {Object.keys(q.by_severity).length > 0 &&
                    ` (${Object.entries(q.by_severity).map(([s, n]) => `${n} ${s}`).join(', ')})`}.
                </span>
              ) : (
                <span>Data quality summary not available{errs.quality_summary ? `: ${errs.quality_summary}` : ''}.</span>
              )}
            </div>
            <Link to="/data-quality" className="text-xs font-semibold text-indigo-600 hover:underline">
              Open Data Quality checks →
            </Link>
          </section>
        </>
      )}
    </div>
  );
};


const GenerateReportButton: React.FC = () => {
  const navigate = useNavigate();
  return (
    <button onClick={() => navigate('/report?autogen=1')}
      className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold transition cursor-pointer">
      Generate report
    </button>
  );
};
