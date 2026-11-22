import React, { useEffect, useState } from 'react';
import { BarChart3 } from 'lucide-react';
import { api } from '../../services/api';
import { useActiveDataset } from '../../contexts/ActiveDatasetContext';
import { WorkspaceGrain } from '../../types/api';
import { BreakdownGrid, ChartSkeleton, ErrorBanner, PageHeader, TrendCard, useWorkspaceData } from './shared';

const GRAIN_LABEL: Record<WorkspaceGrain, string> = { daily: 'Daily', weekly: 'Weekly', monthly: 'Monthly' };

/** Analytics for an uploaded dataset: any measure, daily/weekly/monthly trend, breakdowns. */
export const CustomAnalytics: React.FC = () => {
  const { activeDatasetId, activeDataset } = useActiveDataset();
  const [metric, setMetric] = useState<string | null>(null); // null = server default (primary measure)
  const [grain, setGrain] = useState<WorkspaceGrain>('monthly');

  // A different dataset starts again from its own default metric.
  useEffect(() => {
    setMetric(null);
    setGrain('monthly');
  }, [activeDatasetId]);

  const { data, loading, error, reload } = useWorkspaceData(
    `analytics:${activeDatasetId}:${metric ?? ''}:${grain}`,
    () => api.getDatasetAnalytics(activeDatasetId, { metric, grain }),
    'analytics'
  );
  const errs = data?.section_errors || {};
  const metrics = data?.metrics || [];
  const grains = data?.available_grains || [];
  const selected = metrics.find((m) => m.key === (data?.metric ?? metric));

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        icon={<BarChart3 className="w-4 h-4 text-indigo-600" />}
        title={`Analytics: ${activeDataset?.name || 'Uploaded dataset'}`}
        subtitle={selected ? `${selected.aggregation}(${selected.column ?? '*'}) · ${selected.table}` : 'Pick any measure to analyse'}
        loading={loading}
        cached={data?.cached}
        onRefresh={reload}
      >
        <label className="flex items-center gap-1.5 text-xs text-slate-600">
          Metric
          <select
            aria-label="Metric"
            value={data?.metric ?? metric ?? ''}
            disabled={metrics.length === 0}
            onChange={(e) => setMetric(e.target.value)}
            className="bg-white border border-slate-200 rounded-lg text-xs font-semibold text-slate-700 px-2 py-1.5 max-w-[220px]"
          >
            {metrics.length === 0 && <option value="">Loading…</option>}
            {metrics.map((m) => (
              <option key={m.key} value={m.key}>
                {m.column ? `${m.label} (${m.aggregation})` : m.label}
              </option>
            ))}
          </select>
        </label>
        {grains.length > 0 && (
          <div className="flex rounded-lg border border-slate-200 overflow-hidden" role="group" aria-label="Time grain">
            {grains.map((g) => (
              <button
                key={g}
                onClick={() => setGrain(g)}
                aria-pressed={grain === g}
                className={`px-2.5 py-1.5 text-xs font-semibold cursor-pointer ${
                  grain === g ? 'bg-indigo-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                {GRAIN_LABEL[g]}
              </button>
            ))}
          </div>
        )}
      </PageHeader>
      {error && <ErrorBanner message={error} />}

      {!data && loading && (
        <>
          <ChartSkeleton />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            <ChartSkeleton height="h-56" label=" " />
            <ChartSkeleton height="h-56" label=" " />
            <ChartSkeleton height="h-56" label=" " />
          </div>
        </>
      )}

      {data && (
        <div className={loading ? 'opacity-60 transition-opacity' : ''}>
          <div className="space-y-6">
            <TrendCard
              trend={data.trend}
              reason={errs.trend || (grains.length === 0 ? 'this measure has no date/time column' : undefined)}
              label={`${GRAIN_LABEL[data.grain]} Trend`}
            />
            <BreakdownGrid breakdowns={data.breakdowns} reason={errs.breakdowns} skipped={data.skipped_breakdowns} />
          </div>
        </div>
      )}
    </div>
  );
};
