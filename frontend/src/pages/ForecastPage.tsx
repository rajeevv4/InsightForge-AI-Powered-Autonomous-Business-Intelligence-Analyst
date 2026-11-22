import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Info, LineChart as LineChartIcon } from 'lucide-react';
import { Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../services/api';
import { useActiveDataset } from '../contexts/ActiveDatasetContext';
import { ForecastResponse } from '../types/api';
import { useUi } from '../contexts/UiContext';
import { CurrencyCode, formatCompact, formatMoney, formatNumber } from '../lib/format';
import { EmptyState, InfoTip } from '../components/ui';
import { ChartSkeleton, ErrorBanner, KpiSkeleton, PageHeader, useWorkspaceData } from '../components/workspace/shared';

/*
 * Baseline forecast for the active dataset (Olist demo or an uploaded dataset). All numbers come
 * from the server (deterministic ETS, fixed seed); this page only draws them.
 */

const RELIABILITY_CHIP: Record<string, string> = {
  Good: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  Fair: 'bg-amber-100 text-amber-800 border-amber-200',
  Weak: 'bg-rose-100 text-rose-800 border-rose-200',
};

export const ForecastPage: React.FC = () => {
  const { isOlist, activeDatasetId, activeDataset } = useActiveDataset();
  const [metric, setMetric] = useState<string | null>(null);
  const [horizon, setHorizon] = useState<number>(3);
  const [exclude, setExclude] = useState<boolean>(false);

  useEffect(() => {
    setMetric(null);
    setExclude(false);
  }, [activeDatasetId]);

  const { data, loading, error, reload } = useWorkspaceData<ForecastResponse>(
    `forecast:${activeDatasetId}:${metric ?? ''}:${horizon}:${exclude}`,
    () => (isOlist
      ? api.getOlistForecast({ metric, horizon, excludeAnomalies: exclude })
      : api.getDatasetForecast(activeDatasetId, { metric, horizon, excludeAnomalies: exclude })),
    'forecast'
  );

  // Olist sends R$ for revenue; for uploads the user's picked currency applies to money measures only.
  const { measureCurrency } = useUi();
  const opt = data?.metrics.find((m) => m.key === data?.metric);
  const currency: CurrencyCode = ((data?.currency as CurrencyCode) ||
    (opt ? measureCurrency({ name: opt.label, column: opt.key.split('.').slice(1).join('.'), aggregation: opt.aggregation }) : '')) as CurrencyCode;
  const fmt = (v: number | null | undefined): string => {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const decimals = Math.abs(v) >= 1000 ? 0 : 2;
    return currency ? formatMoney(v, currency, { decimals }) : formatNumber(v, { decimals: Number.isInteger(v) ? 0 : decimals });
  };
  const compact = (v: number) => formatCompact(v, currency);

  const rows = useMemo(() => {
    if (!data) return [];
    const hist = data.history.map((h) => ({ period: h.period, actual: h.value } as Record<string, any>));
    if (data.status === 'ok' && hist.length && data.forecast.length) {
      const last = hist[hist.length - 1];
      last.expected = last.actual; // connect the dashed forecast line to the last actual month
      last.band80 = [last.actual, last.actual];
      last.band95 = [last.actual, last.actual];
    }
    const fc = data.status === 'ok'
      ? data.forecast.map((p) => ({ period: p.period, expected: p.expected, band80: [p.lower_80, p.upper_80], band95: [p.lower_95, p.upper_95] }))
      : [];
    return [...hist, ...fc];
  }, [data]);

  const datasetName = isOlist ? 'Olist demo' : activeDataset?.name || 'dataset';

  return (
    <div className="space-y-5 pb-12">
      <PageHeader
        icon={<LineChartIcon className="w-4 h-4 text-indigo-600" />}
        title="Forecast"
        subtitle={`Baseline forecast for ${datasetName} · deterministic, no AI`}
        loading={loading}
        cached={data?.cached}
        onRefresh={reload}
      >
        <select
          aria-label="Metric"
          value={data?.metric ?? metric ?? ''}
          onChange={(e) => setMetric(e.target.value || null)}
          disabled={!data || data.metrics.length === 0}
          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 bg-white cursor-pointer"
        >
          {(data?.metrics || []).map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
        </select>
        <select
          aria-label="Horizon"
          value={horizon}
          onChange={(e) => setHorizon(Number(e.target.value))}
          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 bg-white cursor-pointer"
        >
          {[1, 2, 3, 4, 5, 6].map((h) => <option key={h} value={h}>{h} month{h > 1 ? 's' : ''} ahead</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer select-none">
          <input type="checkbox" checked={exclude} onChange={(e) => setExclude(e.target.checked)} className="cursor-pointer" />
          Exclude flagged anomaly days
        </label>
      </PageHeader>

      {error && <ErrorBanner message={error} />}
      {loading && !data && (<><KpiSkeleton count={4} /><ChartSkeleton height="h-80" label="Fitting the forecast model..." /></>)}

      {data && (
        <>
          {data.status !== 'ok' ? (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 flex gap-3 animate-fade-in-up" role="status">
              <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
              <div>
                <div className="text-sm font-bold text-amber-900">No forecast for {data.metric_label || 'this metric'}</div>
                <div className="text-xs text-amber-800 mt-0.5">{data.reason}</div>
                {data.backtest && (
                  <div className="text-[11px] text-amber-700 mt-1">
                    Backtest ({data.backtest.holdout}): MAPE {data.backtest.mape?.toFixed(1) ?? '—'}% vs naive {data.backtest.naive_mape?.toFixed(1) ?? '—'}%.
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 min-[420px]:grid-cols-2 lg:grid-cols-4 gap-3 stagger">
              <Card label="Reliability">
                <span className={`px-2 py-0.5 rounded border text-xs font-bold ${RELIABILITY_CHIP[data.reliability || ''] || ''}`}>{data.reliability}</span>
              </Card>
              <Card label="Backtest MAPE" tip="MAPE">
                <span className="text-sm font-bold text-slate-900">{data.backtest?.mape?.toFixed(1)}%</span>
                <span className="text-[11px] text-slate-500 ml-1">vs naive {data.backtest?.naive_mape?.toFixed(1) ?? '—'}%</span><InfoTip term="Naive baseline" className="ml-1" />
                <div className={`text-[11px] ${data.backtest?.beats_naive ? 'text-emerald-700' : 'text-rose-700'}`}>
                  {data.backtest?.beats_naive ? 'beats the naive baseline' : 'does not beat the naive baseline'}
                </div>
              </Card>
              <Card label="Model"><span className="text-[11px] text-slate-700 leading-snug">{data.model}</span></Card>
              <Card label="Training window"><span className="text-xs text-slate-700">{data.training_window}</span></Card>
            </div>
          )}

          <div className="bg-white border border-slate-200/80 rounded-2xl p-4 sm:p-5 min-w-0 animate-fade-in-up">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-3">
              {data.metric_label} by month {data.status === 'ok' ? `· next ${data.horizon} month${data.horizon > 1 ? 's' : ''}` : ''}
            </div>
            {rows.length === 0 ? (
              <EmptyState compact title="No history to show" message="This metric has no dated values yet. Pick another metric, or upload data with a date column." />
            ) : (
              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                    <XAxis dataKey="period" tick={{ fontSize: 10, fill: '#64748b' }} minTickGap={16} />
                    <YAxis tick={{ fontSize: 10, fill: '#64748b' }} width={68} tickFormatter={compact} />
                    <Tooltip
                      formatter={(v: any, name: string) => Array.isArray(v) ? [`${fmt(v[0])} – ${fmt(v[1])}`, name] : [fmt(Number(v)), name]}
                      labelStyle={{ fontSize: 11 }} contentStyle={{ fontSize: 11 }}
                    />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Area dataKey="band95" name="95% band" stroke="none" fill="#6366f1" fillOpacity={0.12} isAnimationActive={false} />
                    <Area dataKey="band80" name="80% band" stroke="none" fill="#6366f1" fillOpacity={0.28} isAnimationActive={false} />
                    <Line className="if-ink-line" dataKey="actual" name="Actual" stroke="#0f172a" strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} />
                    <Line dataKey="expected" name="Forecast" stroke="#6366f1" strokeWidth={2} strokeDasharray="6 4" dot={{ r: 3 }} isAnimationActive={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            )}
            <p className="text-[11px] text-slate-500 mt-2 flex items-center gap-1.5">
              <Info className="w-3.5 h-3.5 shrink-0" />{data.disclaimer}
            </p>
          </div>

          {data.status === 'ok' && (
            <div className="bg-white border border-slate-200/80 rounded-2xl p-4 sm:p-5 overflow-x-auto animate-fade-in-up">
              <div className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-3">Forecast table</div>
              <table className="w-full text-left text-xs">
                <thead className="text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-200">
                  <tr>
                    <th className="py-2 pr-3">Month</th>
                    <th className="py-2 pr-3 text-right">Lower (95%)</th>
                    <th className="py-2 pr-3 text-right">Lower (80%)</th>
                    <th className="py-2 pr-3 text-right">Expected</th>
                    <th className="py-2 pr-3 text-right">Upper (80%)</th>
                    <th className="py-2 text-right">Upper (95%)</th>
                  </tr>
                </thead>
                <tbody>
                  {data.forecast.map((p) => (
                    <tr key={p.period} className="border-b border-slate-100">
                      <td className="py-1.5 pr-3 font-mono whitespace-nowrap">{p.period}</td>
                      <td className="py-1.5 pr-3 text-right text-slate-500">{fmt(p.lower_95)}</td>
                      <td className="py-1.5 pr-3 text-right text-slate-600">{fmt(p.lower_80)}</td>
                      <td className="py-1.5 pr-3 text-right font-bold text-slate-900">{fmt(p.expected)}</td>
                      <td className="py-1.5 pr-3 text-right text-slate-600">{fmt(p.upper_80)}</td>
                      <td className="py-1.5 text-right text-slate-500">{fmt(p.upper_95)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.backtest && data.backtest.points.length > 0 && (
                <div className="mt-4">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">
                    Backtest · {data.backtest.holdout} · naive = {data.backtest.naive_method}
                  </div>
                  <table className="w-full text-left text-[11px]">
                    <tbody>
                      {data.backtest.points.map((b) => (
                        <tr key={b.period} className="border-b border-slate-50">
                          <td className="py-1 pr-3 font-mono whitespace-nowrap">{b.period}</td>
                          <td className="py-1 pr-3">actual {fmt(b.actual)}</td>
                          <td className="py-1 pr-3">model {fmt(b.forecast)}</td>
                          <td className="py-1">naive {fmt(b.naive)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {(data.notes.length > 0 || Object.keys(data.section_errors).length > 0) && (
            <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4 text-[11px] text-slate-600 space-y-1">
              {data.notes.map((n) => <div key={n}>• {n}</div>)}
              {Object.entries(data.section_errors).map(([k, v]) => <div key={k} className="text-amber-700">• {k}: {v}</div>)}
            </div>
          )}
        </>
      )}
    </div>
  );
};

const Card: React.FC<{ label: string; tip?: string; children: React.ReactNode }> = ({ label, tip, children }) => (
  <div className="bg-white border border-slate-200/80 rounded-2xl p-4 min-w-0 card-lift">
    <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1 flex items-center gap-1">{label}{tip && <InfoTip term={tip} />}</div>
    {children}
  </div>
);

export default ForecastPage;
