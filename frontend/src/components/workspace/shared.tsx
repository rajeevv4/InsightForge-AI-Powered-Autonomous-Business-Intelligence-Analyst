import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, BarChart2, Link2, RefreshCw, TrendingUp } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Cell, LabelList, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useUi } from '../../contexts/UiContext';
import { CountUp, InfoTip, TruncatedTick } from '../ui';
import { DashboardBreakdown, DashboardKPI, DashboardSkippedBreakdown, DashboardTrend } from '../../types/api';

/* Shared building blocks for the uploaded-dataset pages. Numbers are plain (no currency). */

export const fmtNumber = (value: number | null | undefined, aggregation?: string): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const isAvg = (aggregation || '').toUpperCase() === 'AVG';
  const isWhole = Number.isInteger(value);
  return new Intl.NumberFormat(undefined, {
    minimumFractionDigits: isAvg ? 2 : 0,
    maximumFractionDigits: isAvg ? 2 : isWhole ? 0 : 2,
  }).format(value);
};

export const fmtCompact = (value: number): string =>
  new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(value);

export const aggLabel = (agg: string): string =>
  ({ SUM: 'Total', AVG: 'Average', COUNT: 'Count', MIN: 'Minimum', MAX: 'Maximum' } as Record<string, string>)[
    (agg || '').toUpperCase()
  ] || agg;

export const measureTitle = (agg: string, label: string): string => {
  const prefix = aggLabel(agg);
  return label.toLowerCase().startsWith(prefix.toLowerCase()) ? label : `${prefix} ${label}`;
};

/** Human message for an API error: server `detail`, plus 403/429/timeouts. */
export const apiErrorMessage = (err: any, what: string): string => {
  const status = err?.response?.status;
  const detail = err?.response?.data?.detail;
  if (status === 429) return 'Too many requests. Please wait a minute and try again.';
  if (status === 403) return typeof detail === 'string' ? detail : 'Access denied for this dataset.';
  if (typeof detail === 'string' && detail) return detail;
  if (err?.code === 'ECONNABORTED') return `Loading ${what} took too long. Please try Refresh.`;
  return `Failed to load ${what}. Please ensure the server is running.`;
};

/**
 * Fetch hook with stale-response protection: only the latest request (for the current
 * `key`) may set state, so switching datasets/params mid-load never shows old data.
 */
export function useWorkspaceData<T>(key: string, fetcher: () => Promise<T>, what: string) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef<number>(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const load = useCallback(async (keepData: boolean) => {
    const reqId = ++latest.current;
    setLoading(true);
    setError(null);
    if (!keepData) setData(null);
    try {
      const result = await fetcherRef.current();
      if (latest.current === reqId) setData(result);
    } catch (err: any) {
      if (latest.current === reqId) {
        setError(apiErrorMessage(err, what));
        setData(null);
      }
    } finally {
      if (latest.current === reqId) setLoading(false);
    }
  }, [what]);

  useEffect(() => {
    load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { data, loading, error, reload: () => load(true) };
}

export const ErrorBanner: React.FC<{ message: string }> = ({ message }) => (
  <div role="alert" className="p-4 bg-amber-50 text-amber-800 text-xs rounded-xl border border-amber-200 flex items-start gap-2 animate-fade-in">
    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
    <span className="break-words min-w-0">{message}</span>
  </div>
);

export const Unavailable: React.FC<{ reason?: string; height?: string }> = ({ reason, height = 'h-40' }) => (
  <div className={`${height} flex flex-col items-center justify-center text-center text-xs text-slate-400 px-4`}>
    <AlertCircle className="w-4 h-4 mb-1.5" />
    <span>Not available{reason ? `: ${reason}` : ''}</span>
  </div>
);

export const PageHeader: React.FC<{
  icon: React.ReactNode; title: string; subtitle: string; loading?: boolean; cached?: boolean; onRefresh?: () => void; children?: React.ReactNode;
}> = ({ icon, title, subtitle, loading, cached, onRefresh, children }) => (
  <div className="flex flex-wrap items-center justify-between gap-3 bg-white/90 backdrop-blur border border-slate-200/80 rounded-2xl p-4 shadow-soft animate-fade-in-up">
    <div className="min-w-0 flex-1 basis-56">
      <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2 min-w-0">
        <span className="shrink-0 w-7 h-7 rounded-lg bg-brand-soft border border-indigo-100 flex items-center justify-center">{icon}</span>
        <span className="truncate" title={title}>{title}</span>
      </h2>
      <p className="text-xs text-slate-500 mt-1 break-words">{subtitle}{cached ? ' · from cache' : ''}</p>
    </div>
    <div className="flex flex-wrap items-center gap-2 min-w-0">
      {children}
      {onRefresh && (
        <button
          onClick={onRefresh}
          disabled={loading}
          aria-label="Refresh"
          className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition cursor-pointer disabled:opacity-60"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      )}
    </div>
  </div>
);

/* ---------------- skeletons (shimmer; shown immediately, so first loads never look frozen) ---------------- */
export const KpiSkeleton: React.FC<{ count?: number }> = ({ count = 4 }) => (
  <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4" aria-label="Loading metrics" aria-busy="true">
    {Array.from({ length: count }).map((_, i) => (
      <div key={i} className="bg-white border border-slate-200/80 rounded-2xl p-4 shadow-xs space-y-2.5">
        <div className="h-2.5 w-24 skeleton rounded" />
        <div className="h-6 w-32 skeleton rounded" />
        <div className="h-2 w-20 skeleton rounded" />
      </div>
    ))}
  </div>
);

export const ChartSkeleton: React.FC<{ height?: string; label?: string }> = ({ height = 'h-64', label }) => (
  <div className={`bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs ${height} flex flex-col`} aria-busy="true">
    <div className="h-2.5 w-28 skeleton rounded mb-4" />
    <div className="flex-1 skeleton rounded-xl flex items-center justify-center text-[10px] text-slate-500 px-4 text-center">
      {label || 'Computing… the first load of a dataset can take a few seconds.'}
    </div>
  </div>
);

/* ---------------- chart helpers (one palette, one tooltip style) ---------------- */
export const CHART_COLORS = ['#4f46e5', '#7c3aed', '#2563eb', '#0891b2', '#059669', '#d97706', '#db2777', '#64748b'];
export const CHART_PRIMARY = CHART_COLORS[0];

export const NiceTooltip: React.FC<any> = ({ active, payload, label, format }) => {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white/95 backdrop-blur px-3 py-2 shadow-lift text-[11px] max-w-[16rem]">
      {label !== undefined && <div className="font-semibold text-slate-800 mb-0.5 break-words">{String(label)}</div>}
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-1.5 text-slate-600">
          <span className="w-2 h-2 rounded-full shrink-0" style={{ background: p.color || p.fill || CHART_PRIMARY }} />
          <span className="truncate">{p.name}:</span>
          <span className="font-semibold text-slate-900 tabular-nums">{format ? format(Number(p.value)) : p.value}</span>
        </div>
      ))}
    </div>
  );
};

/** Averages are not forced from 0, so differences stay visible. */
export const avgDomain = (values: number[]): [number, number] | undefined => {
  const v = values.filter((x) => Number.isFinite(x));
  if (!v.length) return undefined;
  const lo = Math.min(...v), hi = Math.max(...v);
  const pad = (hi - lo) * 0.15 || Math.abs(hi) * 0.05 || 1;
  return [Math.max(0, Math.floor((lo - pad) * 100) / 100), Math.ceil((hi + pad) * 100) / 100];
};

/* ---------------- cards ---------------- */
export const KpiGrid: React.FC<{ kpis: DashboardKPI[] }> = ({ kpis }) => {
  const { fmtMeasure } = useUi();
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4 stagger">
      {kpis.map((k, idx) => {
        const measure = { name: k.label, column: k.column, aggregation: k.aggregation };
        return (
          <div key={`${k.table}.${k.column}.${idx}`} className="group relative overflow-hidden bg-white border border-slate-200/80 rounded-2xl p-4 shadow-xs min-w-0 card-lift">
            <span aria-hidden="true" className="absolute inset-x-0 top-0 h-0.5 bg-brand-gradient opacity-0 group-hover:opacity-100 transition-opacity" />
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500 truncate" title={k.label}>
              {k.column ? measureTitle(k.aggregation, k.label) : k.label}
            </div>
            <div className="text-lg sm:text-xl font-extrabold text-slate-900 mt-1.5 truncate" title={k.value !== null ? fmtMeasure(k.value, measure) : ''}>
              <CountUp value={k.value} format={(v) => fmtMeasure(v, measure)} />
            </div>
            <div className="text-[10px] text-slate-400 mt-1 font-mono truncate" title={`${k.aggregation}(${k.column ?? '*'}) · ${k.table}`}>
              {k.error ? <span className="text-amber-700">{k.error}</span> : `${k.aggregation}(${k.column ?? '*'}) · ${k.table}`}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export const TrendCard: React.FC<{ trend: DashboardTrend | null | undefined; reason?: string; label?: string }> = ({ trend, reason, label = 'Trend' }) => {
  const { fmtMeasure, fmtMeasureCompact } = useUi();
  const measure = trend ? { name: trend.measure_label, column: trend.measure_column, aggregation: trend.aggregation } : undefined;
  const isAvg = (trend?.aggregation || '').toUpperCase() === 'AVG';
  return (
    <section className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs min-w-0 animate-fade-in-up">
      <div className="mb-3 min-w-0">
        <div className="flex items-center space-x-2 text-indigo-600 mb-1">
          <TrendingUp className="w-4 h-4" />
          <span className="text-xs font-bold uppercase tracking-wider">{label}</span>
        </div>
        {trend && (
          <h3 className="text-xs font-bold text-slate-900 break-words">
            {measureTitle(trend.aggregation, trend.measure_label)}: {trend.title.replace(`${trend.measure_label} `, '')} <span className="font-normal text-slate-500 font-mono">({trend.table}.{trend.time_column})</span>
          </h3>
        )}
      </div>
      {trend && trend.points.length > 0 ? (
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={trend.points} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="trendStroke" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#4f46e5" /><stop offset="100%" stopColor="#7c3aed" />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" vertical={false} />
              <XAxis dataKey="period" fontSize={10} stroke="#94a3b8" minTickGap={18} tickLine={false} />
              <YAxis fontSize={10} stroke="#94a3b8" width={64} tickLine={false} axisLine={false}
                domain={isAvg ? avgDomain(trend.points.map((p: any) => Number(p.value))) : undefined}
                tickFormatter={(v) => fmtMeasureCompact(Number(v), measure)} />
              <Tooltip content={<NiceTooltip format={(v: number) => fmtMeasure(v, measure)} />} />
              <Line type="monotone" dataKey="value" name={trend.measure_label} stroke="url(#trendStroke)" strokeWidth={2.5}
                dot={trend.points.length <= 60 ? { r: 2.5, fill: '#4f46e5' } : false} activeDot={{ r: 5 }} animationDuration={900} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <Unavailable reason={reason || 'no data points'} />
      )}
    </section>
  );
};

export const BreakdownCard: React.FC<{ b: DashboardBreakdown }> = ({ b }) => {
  const { fmtMeasure, fmtMeasureCompact } = useUi();
  const measure = { name: b.measure_label, aggregation: b.aggregation };
  const isAvg = b.aggregation.toUpperCase() === 'AVG';
  const data = b.items.map((i) => ({ label: i.label, value: i.value ?? 0 }));
  if (b.other_value !== null && b.other_groups > 0) data.push({ label: `Other (${b.other_groups})`, value: b.other_value });
  return (
    <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs flex flex-col min-w-0 card-lift">
      <div className="mb-3 min-w-0">
        <div className="flex items-center space-x-2 text-indigo-600 mb-1">
          <BarChart2 className="w-4 h-4" />
          <span className="text-xs font-bold uppercase tracking-wider">Breakdown</span>
        </div>
        <h3 className="text-xs font-bold text-slate-900 break-words">{measureTitle(b.aggregation, b.measure_label)} by {b.dimension_label}</h3>
      </div>
      {data.length > 0 ? (
        <div className="w-full" style={{ height: Math.max(160, data.length * 30) }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ left: 4, right: 52, top: 4, bottom: 4 }} barCategoryGap="22%">
              <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" horizontal={false} />
              <XAxis type="number" fontSize={10} stroke="#94a3b8" tickLine={false}
                domain={isAvg ? avgDomain(data.map((d) => d.value)) : undefined} allowDataOverflow={isAvg}
                tickFormatter={(v) => fmtMeasureCompact(Number(v), measure)} />
              {/* Every category is labelled (interval 0); long labels are truncated with a hover tooltip */}
              <YAxis type="category" dataKey="label" width={96} interval={0} tickLine={false} axisLine={false}
                tick={<TruncatedTick max={14} />} />
              <Tooltip cursor={{ fill: 'rgba(99,102,241,0.06)' }} content={<NiceTooltip format={(v: number) => fmtMeasure(v, measure)} />} />
              <Bar dataKey="value" name={measureTitle(b.aggregation, b.measure_label)} radius={[0, 6, 6, 0]} animationDuration={800}>
                {data.map((d, i) => <Cell key={d.label} fill={d.label.startsWith('Other (') ? '#cbd5e1' : CHART_COLORS[i % 3]} />)}
                <LabelList dataKey="value" position="right" fontSize={10} fill="#475569" formatter={(v: any) => fmtMeasureCompact(Number(v), measure)} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <Unavailable reason="no rows" />
      )}
      <div className="mt-3 space-y-1 text-[10px] text-slate-500 min-w-0">
        {b.total_value !== null && (
          <div>
            All groups total: <span className="font-semibold text-slate-700">{fmtMeasure(b.total_value, measure)}</span>
          </div>
        )}
        {isAvg && <div>Average per group; groups beyond the top {b.items.length} are not shown. Axis starts near the smallest value.</div>}
        {b.join_path && (
          <div className="flex items-start gap-1 min-w-0">
            <Link2 className="w-3 h-3 shrink-0 mt-px" />
            <span className="font-mono break-all">{b.join_path}</span>
            <InfoTip term="N:1" />
          </div>
        )}
        {b.truncated && <div className="text-amber-700">Too many groups; only the first 500 were aggregated.</div>}
      </div>
    </div>
  );
};

export const SkippedList: React.FC<{ skipped: DashboardSkippedBreakdown[] }> = ({ skipped }) =>
  skipped.length === 0 ? null : (
    <div className="mt-3 p-3 bg-slate-50 border border-slate-200/80 rounded-xl text-[10px] text-slate-600 space-y-1">
      <div className="font-semibold text-slate-700">Skipped to avoid unsafe joins or errors:</div>
      {skipped.map((s) => (
        <div key={s.dimension}>
          <span className="font-mono">{s.dimension}</span>: {s.reason}
        </div>
      ))}
    </div>
  );

export const BreakdownGrid: React.FC<{ breakdowns: DashboardBreakdown[] | null | undefined; reason?: string; skipped?: DashboardSkippedBreakdown[] }> = ({ breakdowns, reason, skipped = [] }) => (
  <section>
    <div className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-2.5">Breakdowns</div>
    {breakdowns && breakdowns.length > 0 ? (
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-5 stagger">
        {breakdowns.map((b) => (
          <BreakdownCard key={`${b.dimension_table}.${b.dimension_column}.${b.measure_label}`} b={b} />
        ))}
      </div>
    ) : (
      <div className="bg-white border border-slate-200/80 rounded-2xl shadow-xs">
        <Unavailable reason={reason} />
      </div>
    )}
    <SkippedList skipped={skipped} />
  </section>
);
