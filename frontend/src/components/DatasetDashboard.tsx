import React, { useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  BarChart2,
  Database,
  LayoutDashboard,
  Link2,
  RefreshCw,
  ShieldAlert,
  TrendingUp,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api } from '../services/api';
import { DashboardBreakdown, DatasetDashboardResponse } from '../types/api';
import { BreakdownCard as SharedBreakdownCard } from './workspace/shared';
import { useUi } from '../contexts/UiContext';
import { CountUp, InfoTip } from './ui';
import { AnomalyExplainDrawer, ExplainButton, ExplainTarget } from './AnomalyExplainDrawer';

/**
 * Deterministic dashboard for an UPLOADED dataset (never shown for the Olist demo).
 * Data comes from GET /api/datasets/{id}/dashboard; no AI is involved.
 * Numbers are shown plain (no currency symbol) because uploaded data has no known currency.
 */

const fmtNumber = (value: number | null | undefined, aggregation?: string): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const isAvg = (aggregation || '').toUpperCase() === 'AVG';
  const isWhole = Number.isInteger(value);
  return new Intl.NumberFormat(undefined, {
    minimumFractionDigits: isAvg ? 2 : 0,
    maximumFractionDigits: isAvg ? 2 : isWhole ? 0 : 2,
  }).format(value);
};

const fmtCompact = (value: number): string =>
  new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(value);

const aggLabel = (agg: string): string =>
  ({ SUM: 'Total', AVG: 'Average', COUNT: 'Count', MIN: 'Minimum', MAX: 'Maximum' } as Record<string, string>)[
    agg.toUpperCase()
  ] || agg;

// "Total" + "Total Amount" -> "Total Amount"; "Average" + "Customer Rating" -> "Average Customer Rating"
const measureTitle = (agg: string, label: string): string => {
  const prefix = aggLabel(agg);
  return label.toLowerCase().startsWith(prefix.toLowerCase()) ? label : `${prefix} ${label}`;
};

const severityClass = (sev: string): string =>
  sev === 'high'
    ? 'bg-rose-100 text-rose-800'
    : sev === 'medium'
    ? 'bg-amber-100 text-amber-800'
    : 'bg-slate-100 text-slate-700';

const Unavailable: React.FC<{ reason?: string }> = ({ reason }) => (
  <div className="h-40 flex flex-col items-center justify-center text-center text-xs text-slate-400 px-4">
    <AlertCircle className="w-4 h-4 mb-1.5" />
    <span>Not available{reason ? `: ${reason}` : ''}</span>
  </div>
);

const SectionTitle: React.FC<{ icon: React.ReactNode; label: string; title?: string; tip?: string }> = ({ icon, label, title, tip }) => (
  <div className="mb-3">
    <div className="flex items-center space-x-2 text-indigo-600 mb-1">
      {icon}
      <span className="text-xs font-bold uppercase tracking-wider">{label}</span>
    </div>
    {title && <h3 className="text-xs font-bold text-slate-900 break-words">{title}{tip && <InfoTip term={tip} className="ml-1" />}</h3>}
  </div>
);

const BreakdownCard: React.FC<{ b: DashboardBreakdown }> = ({ b }) => <SharedBreakdownCard b={b} />;

export const DatasetDashboard: React.FC<{ datasetId: string }> = ({ datasetId }) => {
  const { fmtMeasure, fmtMeasureCompact } = useUi();
  const [dashboard, setDashboard] = useState<DatasetDashboardResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [explainTarget, setExplainTarget] = useState<ExplainTarget | null>(null);
  // Latest requested dataset; responses for any other dataset are ignored (user switched mid-load).
  const requestedIdRef = useRef<string>(datasetId);

  const load = async (id: string) => {
    requestedIdRef.current = id;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getDatasetDashboard(id);
      if (requestedIdRef.current !== id) return;
      setDashboard(data);
    } catch (err: any) {
      if (requestedIdRef.current !== id) return;
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      if (status === 429) {
        setError('Too many requests. Please wait a minute and refresh the dashboard.');
      } else if (typeof detail === 'string' && detail) {
        setError(detail);
      } else if (err?.code === 'ECONNABORTED') {
        setError('The dashboard took too long to load. Please try Refresh.');
      } else {
        setError('Failed to load the dashboard. Please ensure the server is running.');
      }
      setDashboard(null);
    } finally {
      if (requestedIdRef.current === id) setLoading(false);
    }
  };

  useEffect(() => {
    setDashboard(null);
    load(datasetId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId]);

  const errs = dashboard?.section_errors || {};
  const kpis = dashboard?.kpis || [];
  const trend = dashboard?.trend;
  const breakdowns = dashboard?.breakdowns || [];
  const quality = dashboard?.data_quality || [];
  const anomalies = dashboard?.anomalies;
  const totalFindings = quality.reduce((n, t) => n + t.findings.length, 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between bg-white border border-slate-200/80 rounded-2xl p-4 shadow-xs">
        <div>
          <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <LayoutDashboard className="w-4 h-4 text-indigo-600" />
            Dataset Dashboard
          </h2>
          <p className="text-xs text-slate-500">
            Deterministic KPIs, monthly trend, breakdowns, data quality and anomalies computed from your dataset. No AI involved.
          </p>
        </div>
        <button
          onClick={() => load(datasetId)}
          disabled={loading}
          className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition cursor-pointer disabled:opacity-60"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {error && (
        <div className="p-4 bg-amber-50 text-amber-800 text-xs rounded-xl border border-amber-200 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {loading && !dashboard && (
        <div className="bg-white border border-slate-200/80 rounded-2xl p-10 shadow-xs flex flex-col items-center justify-center text-xs text-slate-500">
          <RefreshCw className="w-5 h-5 animate-spin text-indigo-600 mb-2" />
          Building dashboard… this can take a few seconds.
        </div>
      )}

      {dashboard && (
        <>
          {/* 1. KPI cards */}
          <section>
            <div className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-2.5">Key Metrics</div>
            {kpis.length > 0 ? (
              <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
                {kpis.map((k, idx) => (
                  <div key={`${k.table}.${k.column}.${idx}`} className="bg-white border border-slate-200/80 rounded-2xl p-4 shadow-xs">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500 truncate" title={k.label}>
                      {k.column ? measureTitle(k.aggregation, k.label) : k.label}
                    </div>
                    <div className="text-xl font-extrabold text-slate-900 mt-1.5 truncate" title={k.value !== null ? String(k.value) : ''}>
                      <CountUp value={k.value} format={(v) => fmtMeasure(v, { name: k.label, column: k.column, aggregation: k.aggregation })} />
                    </div>
                    <div className="text-[10px] text-slate-400 mt-1 font-mono truncate">
                      {k.error ? <span className="text-amber-700">{k.error}</span> : `${k.aggregation}(${k.column ?? '*'}) · ${k.table}`}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="bg-white border border-slate-200/80 rounded-2xl shadow-xs">
                <Unavailable reason={errs.kpis || 'no measures found'} />
              </div>
            )}
          </section>

          {/* 2. Trend */}
          <section className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
            <SectionTitle
              icon={<TrendingUp className="w-4 h-4" />}
              label="Monthly Trend"
              title={trend ? `${measureTitle(trend.aggregation, trend.measure_label)} by month (${trend.table}.${trend.time_column})` : undefined}
            />
            {trend && trend.points.length > 0 ? (
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trend.points}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="period" fontSize={9} stroke="#94a3b8" tickFormatter={(p) => String(p).slice(0, 7)} />
                    <YAxis fontSize={10} stroke="#94a3b8" width={60} tickFormatter={(v) => fmtMeasureCompact(Number(v), { name: trend.measure_label, column: trend.measure_column, aggregation: trend.aggregation })} />
                    <Tooltip formatter={(v) => fmtMeasure(Number(v), { name: trend.measure_label, column: trend.measure_column, aggregation: trend.aggregation })} labelFormatter={(p) => String(p).slice(0, 7)} />
                    <Line type="monotone" dataKey="value" name={trend.measure_label} stroke="#4f46e5" strokeWidth={2} dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <Unavailable reason={errs.trend || 'no data points'} />
            )}
          </section>

          {/* 3. Breakdowns */}
          <section>
            <div className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-2.5">Breakdowns</div>
            {breakdowns.length > 0 ? (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                {breakdowns.map((b) => (
                  <BreakdownCard key={`${b.dimension_table}.${b.dimension_column}`} b={b} />
                ))}
              </div>
            ) : (
              <div className="bg-white border border-slate-200/80 rounded-2xl shadow-xs">
                <Unavailable reason={errs.breakdowns} />
              </div>
            )}
            {dashboard.skipped_breakdowns.length > 0 && (
              <div className="mt-3 p-3 bg-slate-50 border border-slate-200/80 rounded-xl text-[10px] text-slate-600 space-y-1">
                <div className="font-semibold text-slate-700">Skipped to avoid unsafe joins or errors:</div>
                {dashboard.skipped_breakdowns.map((s) => (
                  <div key={s.dimension}>
                    <span className="font-mono">{s.dimension}</span>: {s.reason}
                  </div>
                ))}
              </div>
            )}
          </section>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* 4. Data quality */}
            <section className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
              <SectionTitle icon={<ShieldAlert className="w-4 h-4" />} label="Data Quality" title={`${totalFindings} finding${totalFindings === 1 ? '' : 's'} across ${quality.length} table${quality.length === 1 ? '' : 's'}`} />
              {dashboard.data_quality ? (
                <div className="space-y-3">
                  {quality.map((t) => (
                    <div key={t.table}>
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-800">
                        <Database className="w-3.5 h-3.5 text-slate-400" />
                        {t.table}
                        <span className="text-[10px] font-normal text-slate-400">({fmtNumber(t.row_count)} rows)</span>
                      </div>
                      {t.findings.length === 0 ? (
                        <div className="text-[10px] text-emerald-700 ml-5 mt-1">No issues found.</div>
                      ) : (
                        <ul className="ml-5 mt-1 space-y-1">
                          {t.findings.map((f, i) => (
                            <li key={i} className="text-[10px] text-slate-600 flex items-start gap-1.5">
                              <span className={`px-1.5 py-0.5 rounded font-semibold capitalize shrink-0 ${severityClass(f.severity)}`}>{f.severity}</span>
                              <span>{f.message}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <Unavailable reason={errs.data_quality} />
              )}
            </section>

            {/* 5. Anomalies */}
            <section className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
              <SectionTitle
                icon={<AlertCircle className="w-4 h-4" />}
                label="Anomalies"
                title={anomalies ? `Unusual days in ${anomalies.measure_label ?? 'the primary measure'} (rolling MAD z-score)` : undefined}
                tip="MAD"
              />
              {anomalies ? (
                anomalies.items.length > 0 ? (
                  <div className="overflow-x-auto max-h-72 overflow-y-auto">
                    <table className="w-full text-left text-[10px]">
                      <thead className="text-slate-500 uppercase tracking-wider border-b border-slate-200">
                        <tr>
                          <th className="py-1.5 pr-2">Day</th>
                          <th className="py-1.5 pr-2 text-right">Observed</th>
                          <th className="py-1.5 pr-2 text-right">Expected</th>
                          <th className="py-1.5 pr-2">Direction</th>
                          <th className="py-1.5 pr-2">Severity</th>
                          <th className="py-1.5">Why?</th>
                        </tr>
                      </thead>
                      <tbody>
                        {anomalies.items.map((a) => (
                          <tr key={a.period} className="border-b border-slate-100">
                            <td className="py-1.5 pr-2 font-mono">{a.period}</td>
                            <td className="py-1.5 pr-2 text-right tabular-nums">{fmtMeasure(a.observed, { name: anomalies.measure_label, aggregation: 'SUM' })}</td>
                            <td className="py-1.5 pr-2 text-right text-slate-500 tabular-nums">{fmtMeasure(a.expected, { name: anomalies.measure_label, aggregation: 'SUM' })}</td>
                            <td className={`py-1.5 pr-2 capitalize ${a.direction === 'spike' ? 'text-emerald-700' : 'text-rose-700'}`}>{a.direction}</td>
                            <td className="py-1.5 pr-2">
                              <span className={`px-1.5 py-0.5 rounded font-semibold capitalize ${severityClass(a.severity)}`}>{a.severity}</span>
                            </td>
                            <td className="py-1.5">
                              <ExplainButton compact onClick={() => setExplainTarget({
                                source: { kind: 'dataset', datasetId }, metric: dashboard?.primary_measure ?? null,
                                period: a.period, grain: 'daily',
                              })} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="text-xs text-slate-500 py-6 text-center">{anomalies.note || 'No anomalies flagged.'}</div>
                )
              ) : (
                <Unavailable reason={errs.anomalies} />
              )}
            </section>
          </div>
        </>
      )}
      <AnomalyExplainDrawer target={explainTarget} onClose={() => setExplainTarget(null)} />
    </div>
  );
};
