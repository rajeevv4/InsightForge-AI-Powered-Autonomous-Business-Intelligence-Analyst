import React, { useEffect, useMemo, useRef, useState } from 'react';
import { HelpCircle, Layers, Search, TrendingDown, TrendingUp, X } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../services/api';
import { AnomalyExplanationResponse, ExplainSource, WaterfallStep } from '../types/api';
import { useUi } from '../contexts/UiContext';
import { CurrencyCode, currencyizeSentence, formatMoney } from '../lib/format';
import { InfoTip } from './ui';

/*
 * "Explain this anomaly" drawer. Every number and sentence comes from the server, which computes them
 * deterministically (no LLM). The waterfall is a stacked BarChart: an invisible "base" series lifts each
 * floating step to where the previous one ended.
 */

export interface ExplainTarget {
  source: ExplainSource;
  metric?: string | null;
  period: string;
  grain: 'daily' | 'weekly';
}

const STEP_COLOR: Record<string, string> = {
  total: '#6366f1', // indigo: Expected / Observed
  up: '#10b981',    // green: positive contribution
  down: '#ef4444',  // red: negative contribution
  other: '#94a3b8', // slate: all other groups
};

const errorMessage = (err: any): string => {
  const status = err?.response?.status;
  const detail = err?.response?.data?.detail;
  if (status === 429) return 'Too many explain requests. Please wait a minute and try again.';
  if (status === 403) return typeof detail === 'string' ? detail : 'Access denied for this dataset.';
  if (err?.code === 'ECONNABORTED') return 'The explanation took too long (the database may be busy). Please try again.';
  if (typeof detail === 'string' && detail) return detail;
  return 'Could not load the explanation. Please ensure the server is running.';
};

export const ExplainButton: React.FC<{ onClick: () => void; compact?: boolean }> = ({ onClick, compact }) => (
  <button
    type="button"
    onClick={onClick}
    className={`inline-flex items-center gap-1 rounded-md border border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 font-semibold cursor-pointer transition ${
      compact ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-1 text-[11px]'
    }`}
    title="Why did this happen? Break the change down by dimension"
  >
    <Search className="w-3 h-3" />
    Explain
  </button>
);

export const AnomalyExplainDrawer: React.FC<{ target: ExplainTarget | null; onClose: () => void }> = ({ target, onClose }) => {
  const [data, setData] = useState<AnomalyExplanationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState(0);
  const latest = useRef(0);

  const key = target ? `${target.source.kind}|${target.source.kind === 'dataset' ? target.source.datasetId : ''}|${target.metric || ''}|${target.period}|${target.grain}` : '';

  useEffect(() => {
    if (!target) return;
    const reqId = ++latest.current; // ignore stale responses (another row / dataset clicked meanwhile)
    setLoading(true);
    setError(null);
    setData(null);
    setTab(0);
    const p = target.source.kind === 'olist'
      ? api.explainOlistAnomaly(target.metric || 'gross_revenue', target.period, target.grain)
      : api.explainDatasetAnomaly(target.source.datasetId, target.period, { metric: target.metric, grain: target.grain });
    p.then((res) => { if (latest.current === reqId) setData(res); })
      .catch((err) => { if (latest.current === reqId) setError(errorMessage(err)); })
      .finally(() => { if (latest.current === reqId) setLoading(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    if (!target) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [target, onClose]);

  // Invalidate any in-flight request when the drawer closes.
  useEffect(() => { if (!target) latest.current += 1; }, [target]);

  // Uploaded datasets: the server sends no currency; use the one the user picked for this dataset (money measures only).
  const { measureCurrency } = useUi();

  if (!target) return null;

  const pickedCurrency: CurrencyCode = data && !data.currency && data.unit === 'number'
    ? measureCurrency({ name: data.metric_label, column: data.metric.split('.').slice(1).join('.'), aggregation: data.additive ? 'SUM' : 'AVG' })
    : '';
  const effectiveCurrency: CurrencyCode = ((data?.unit === 'currency' ? data?.currency : '') || pickedCurrency || '') as CurrencyCode;
  // Sentences: the server text already has R$ for Olist; add the picked currency for uploads.
  const say = (t: string) => (pickedCurrency ? currencyizeSentence(t, pickedCurrency) : t);

  const fmt = (v: number | null | undefined, signed = false): string => {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const unit = data?.unit || 'number';
    const cur = effectiveCurrency;
    const a = Math.abs(v);
    const sign = signed ? (v >= 0 ? '+' : '-') : v < 0 ? '-' : '';
    if (unit === 'percent') return signed ? `${sign}${a.toFixed(1)} pts` : `${v.toFixed(1)}%`;
    const digits = unit === 'score' ? 2 : unit === 'count' ? (Number.isInteger(a) ? 0 : 1) : a >= 1000 || Number.isInteger(a) ? 0 : 2;
    if (cur && (unit === 'currency' || unit === 'number')) return `${sign}${formatMoney(a, cur, { decimals: digits })}`;
    const body = new Intl.NumberFormat('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(a);
    return `${sign}${body}`;
  };

  const direction = data?.headline?.direction || 'change';
  const title = data
    ? `Why did ${data.metric_label.toLowerCase()} ${direction === 'drop' ? 'drop' : direction === 'spike' ? 'spike' : 'change'} ${data.grain === 'weekly' ? 'in the week of' : 'on'} ${data.period}?`
    : `Why did this ${target.grain === 'weekly' ? 'week' : 'day'} (${target.period}) look unusual?`;
  const dim = data?.dimensions[Math.min(tab, Math.max(0, (data?.dimensions.length || 1) - 1))];

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="Explain this anomaly">
      <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px] animate-fade-in" onClick={onClose} />
      <div className="relative h-full w-full max-w-3xl bg-white shadow-2xl overflow-y-auto overflow-x-hidden animate-slide-in-right">
        <div className="sticky top-0 z-10 bg-white border-b border-slate-200 px-5 py-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[10px] font-bold uppercase tracking-wider text-indigo-600">Explain this anomaly</div>
            <h2 className="text-base font-bold text-slate-900 leading-snug">{title}</h2>
            {data && (
              <div className="text-[11px] text-slate-500 mt-0.5">
                {data.dataset_name} · baseline {data.baseline_window} · deterministic, no AI
                {data.cached ? ' · cached' : ''}
              </div>
            )}
          </div>
          <button onClick={onClose} className="shrink-0 p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 cursor-pointer" aria-label="Close explanation">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {loading && <DrawerSkeleton />}
          {error && !loading && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 text-rose-800 text-xs p-3">{error}</div>
          )}

          {data && !loading && (
            <>
              {/* (a) headline */}
              {data.headline ? (
                <div className="rounded-2xl border border-slate-200 p-4">
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <Stat label="Observed" value={fmt(data.headline.observed)} strong />
                    <Stat label="Expected" value={fmt(data.headline.expected)} />
                    <Stat label="Change" value={fmt(data.headline.change_abs, true)}
                          tone={data.headline.change_abs >= 0 ? 'up' : 'down'} />
                    <Stat label="Change %" value={data.headline.change_pct == null ? '—' : `${data.headline.change_pct >= 0 ? '+' : ''}${data.headline.change_pct.toFixed(1)}%`}
                          tone={data.headline.change_abs >= 0 ? 'up' : 'down'} />
                  </div>
                  <div className="mt-3 flex items-start gap-2 text-xs text-slate-700">
                    {data.headline.direction === 'drop'
                      ? <TrendingDown className="w-4 h-4 text-rose-600 shrink-0" />
                      : <TrendingUp className="w-4 h-4 text-emerald-600 shrink-0" />}
                    <span>{pickedCurrency
                      ? `${data.metric_label} was ${fmt(data.headline.observed)} ${data.grain === 'weekly' ? 'in the week of' : 'on'} ${data.period} vs ${fmt(data.headline.expected)} expected: ${fmt(data.headline.change_abs, true)}${data.headline.change_pct != null ? `, ${data.headline.change_pct >= 0 ? '+' : ''}${data.headline.change_pct.toFixed(1)}%` : ''}.`
                      : data.headline.sentence}</span>
                  </div>
                </div>
              ) : (
                <SectionError what="Headline" reason={data.section_errors.headline} />
              )}

              {/* (b) + (c) waterfall with one tab per dimension, best first */}
              {data.dimensions.length > 0 ? (
                <div className="rounded-2xl border border-slate-200 p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Layers className="w-4 h-4 text-indigo-600" />
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-700">Root-cause waterfall</span><InfoTip term="Mix shift" />
                  </div>
                  <div className="flex flex-wrap gap-1.5 mb-3" role="tablist">
                    {data.dimensions.map((d, i) => (
                      <button key={d.key} role="tab" aria-selected={i === tab} onClick={() => setTab(i)}
                        className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold border cursor-pointer ${
                          i === tab ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                        }`}>
                        {d.label}
                        <span className={`ml-1 font-normal ${i === tab ? 'text-indigo-100' : 'text-slate-400'}`}>
                          top 3 = {Math.round(d.explanatory_power * 100)}%
                        </span>
                      </button>
                    ))}
                  </div>
                  {dim && (
                    <>
                      <Waterfall steps={dim.waterfall} fmt={fmt} zeroBased={data.additive} />
                      <p className="text-[11px] text-slate-600 mt-2">{dim.summary}</p>
                      {dim.join_path && <p className="text-[10px] text-slate-400 mt-1">Joined via {dim.join_path}</p>}
                      <div className="overflow-x-auto mt-3">
                        <table className="w-full text-left text-[11px]">
                          <thead className="text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-200">
                            <tr>
                              <th className="py-1.5 pr-2">{dim.label}</th>
                              <th className="py-1.5 pr-2 text-right">{data.additive ? 'Observed' : 'Part now'}</th>
                              <th className="py-1.5 pr-2 text-right">{data.additive ? 'Expected' : 'Part before'}</th>
                              <th className="py-1.5 pr-2 text-right">Contribution</th>
                              <th className="py-1.5 text-right">Share</th>
                            </tr>
                          </thead>
                          <tbody>
                            {dim.drivers.map((d) => (
                              <tr key={d.label} className="border-b border-slate-100">
                                <td className="py-1.5 pr-2 font-medium text-slate-800">{d.label}</td>
                                <td className="py-1.5 pr-2 text-right">{fmt(d.observed)}</td>
                                <td className="py-1.5 pr-2 text-right text-slate-500">{fmt(d.expected)}</td>
                                <td className={`py-1.5 pr-2 text-right font-semibold ${d.contribution >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
                                  {fmt(d.contribution, true)}
                                </td>
                                <td className="py-1.5 text-right text-slate-500">
                                  {d.share_of_change_pct == null ? '—' : `${d.share_of_change_pct.toFixed(0)}%`}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {dim.other_groups > 0 && (
                          <div className="text-[10px] text-slate-400 mt-1">
                            + {dim.other_groups} more group{dim.other_groups === 1 ? '' : 's'} in "All other" ({fmt(dim.other_contribution, true)})
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </div>
              ) : (
                <SectionError what="Waterfall" reason={data.section_errors.dimensions || 'No dimension could be analysed.'} />
              )}

              {/* (d) top drivers */}
              {data.top_drivers.length > 0 && (
                <div className="rounded-2xl border border-slate-200 p-4">
                  <div className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">Top drivers</div>
                  <ul className="space-y-1.5">
                    {data.top_drivers.map((t, i) => (
                      <li key={`${t.dimension}-${t.label}-${i}`} className="flex items-start gap-2 text-xs text-slate-700">
                        <span className={`mt-1 w-2 h-2 rounded-full shrink-0 ${t.contribution >= 0 ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                        <span>{say(t.sentence)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* (e) volume vs value */}
              {data.volume_value ? (
                <div className="rounded-2xl border border-slate-200 p-4">
                  <div className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-3 flex items-center gap-1">Volume vs value <InfoTip term="Volume vs value" /></div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <EffectCard title={`Volume (${data.volume_value.volume_label})`}
                      main={fmt(data.volume_value.volume_effect, true)} positive={data.volume_value.volume_effect >= 0}
                      sub={`${new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(data.volume_value.volume_observed)} vs ${new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(data.volume_value.volume_expected)} expected`}
                      dominant={data.volume_value.dominant === 'volume'} />
                    <EffectCard title={`Value (${data.volume_value.value_label})`}
                      main={fmt(data.volume_value.value_effect, true)} positive={data.volume_value.value_effect >= 0}
                      sub={`${fmt(data.volume_value.value_observed)} vs ${fmt(data.volume_value.value_expected)} in the baseline`}
                      dominant={data.volume_value.dominant === 'value'} />
                  </div>
                  <ul className="mt-3 space-y-1 text-xs text-slate-600 list-disc pl-4">
                    {data.volume_value.sentences.map((s, i) => <li key={s}>{i === 1 && pickedCurrency
                      ? `Value: ${data.volume_value!.value_label} ${fmt(data.volume_value!.value_observed)} vs ${fmt(data.volume_value!.value_expected)} in the baseline, worth ${fmt(data.volume_value!.value_effect, true)}.`
                      : say(s)}</li>)}
                  </ul>
                </div>
              ) : (
                data.section_errors.volume_value && (
                  <SectionError what="Volume vs value" reason={data.section_errors.volume_value} muted />
                )
              )}

              {(data.skipped_dimensions.length > 0 || data.notes.length > 0) && (
                <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4 text-[11px] text-slate-600 space-y-1">
                  {data.notes.map((n) => (
                    <div key={n} className="flex gap-1.5"><HelpCircle className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-px" />{n}</div>
                  ))}
                  {data.skipped_dimensions.map((s) => (
                    <div key={s.dimension}><span className="font-semibold">Skipped {s.dimension}:</span> {s.reason}</div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

const Stat: React.FC<{ label: string; value: string; strong?: boolean; tone?: 'up' | 'down' }> = ({ label, value, strong, tone }) => (
  <div>
    <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">{label}</div>
    <div className={`text-sm font-mono ${strong ? 'font-bold text-slate-900' : 'text-slate-700'} ${
      tone === 'up' ? 'text-emerald-700 font-semibold' : tone === 'down' ? 'text-rose-700 font-semibold' : ''
    }`}>{value}</div>
  </div>
);

const EffectCard: React.FC<{ title: string; main: string; sub: string; positive: boolean; dominant: boolean }> = ({ title, main, sub, positive, dominant }) => (
  <div className={`rounded-xl border p-3 ${dominant ? 'border-indigo-300 bg-indigo-50/50' : 'border-slate-200'}`}>
    <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
      {title}{dominant && <span className="ml-1 text-indigo-600">· main effect</span>}
    </div>
    <div className={`text-base font-bold font-mono ${positive ? 'text-emerald-700' : 'text-rose-700'}`}>{main}</div>
    <div className="text-[11px] text-slate-500">{sub}</div>
  </div>
);

const SectionError: React.FC<{ what: string; reason?: string; muted?: boolean }> = ({ what, reason, muted }) => (
  <div className={`rounded-xl border p-3 text-xs ${muted ? 'border-slate-200 bg-slate-50 text-slate-500' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
    <span className="font-semibold">{what} unavailable:</span> {reason || 'not computed'}
  </div>
);

const DrawerSkeleton: React.FC = () => (
  <div className="space-y-4 animate-pulse" aria-label="Loading explanation">
    <div className="h-24 rounded-2xl bg-slate-100" />
    <div className="h-72 rounded-2xl bg-slate-100" />
    <div className="h-20 rounded-2xl bg-slate-100" />
    <div className="text-[11px] text-slate-400 text-center">Breaking the change down by every dimension...</div>
  </div>
);

const Waterfall: React.FC<{ steps: WaterfallStep[]; fmt: (v: number, signed?: boolean) => string; zeroBased: boolean }> = ({ steps, fmt, zeroBased }) => {
  const rows = useMemo(() => steps.map((s) => {
    const lo = s.kind === 'total' ? Math.min(0, s.end) : Math.min(s.start, s.end);
    const hi = s.kind === 'total' ? Math.max(0, s.end) : Math.max(s.start, s.end);
    return { name: s.name.length > 16 ? `${s.name.slice(0, 15)}…` : s.name, full: s.name, base: lo, size: hi - lo, kind: s.kind, value: s.value };
  }), [steps]);
  const domain = useMemo<[number | string, number | string]>(() => {
    if (zeroBased) return [0, 'auto'];
    // Rates/averages: zoom in on the range the steps move through.
    const vals = steps.flatMap((s) => (s.kind === 'total' ? [s.end] : [s.start, s.end]));
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = (hi - lo) * 0.15 || Math.abs(hi) * 0.05 || 1;
    return [Number((lo - pad).toFixed(4)), Number((hi + pad).toFixed(4))];
  }, [steps, zeroBased]);

  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 8, left: 8, bottom: 40 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
          <XAxis dataKey="name" interval={0} angle={-30} textAnchor="end" tick={{ fontSize: 10, fill: '#475569' }} height={50} />
          <YAxis domain={domain} allowDataOverflow tick={{ fontSize: 10, fill: '#64748b' }} width={70}
                 tickFormatter={(v: number) => new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(v)} />
          <Tooltip
            cursor={{ fill: '#f1f5f9' }}
            content={({ active, payload }) => {
              if (!active || !payload || !payload.length) return null;
              const r: any = payload[0].payload;
              return (
                <div className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] shadow">
                  <div className="font-semibold text-slate-800">{r.full}</div>
                  <div className="text-slate-600">{r.kind === 'total' ? fmt(r.value) : fmt(r.value, true)}</div>
                </div>
              );
            }}
          />
          <Bar dataKey="base" stackId="w" fill="transparent" isAnimationActive={false} />
          <Bar dataKey="size" stackId="w" isAnimationActive={false} radius={[3, 3, 0, 0]}>
            {rows.map((r, i) => <Cell key={`c-${i}`} fill={STEP_COLOR[r.kind] || STEP_COLOR.other} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

export default AnomalyExplainDrawer;
