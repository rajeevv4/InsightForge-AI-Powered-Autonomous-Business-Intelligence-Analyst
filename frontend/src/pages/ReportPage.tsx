import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AlertTriangle, Download, FileText, Loader2, Play } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../services/api';
import { useActiveDataset } from '../contexts/ActiveDatasetContext';
import { ReportResponse } from '../types/api';
import { useUi } from '../contexts/UiContext';
import { currencyizeSentence, parseDisplayNumber } from '../lib/format';
import { CheckCircle2, CircleDashed } from 'lucide-react';

/*
 * One-click report for the active dataset. The server builds every number and sentence
 * deterministically (fixed templates); this page previews the JSON and downloads the PDF.
 */

const STATUS_CHIP: Record<string, string> = {
  PASS: 'bg-emerald-100 text-emerald-800',
  WARN: 'bg-amber-100 text-amber-800',
  FAIL: 'bg-rose-100 text-rose-800',
};

/** Error text for JSON and blob (PDF) responses alike: server `detail`, 403, 429, timeouts. */
const errorText = async (err: any, what: string): Promise<string> => {
  const status = err?.response?.status;
  let detail = err?.response?.data?.detail;
  const data = err?.response?.data;
  if (!detail && data instanceof Blob) {
    try { detail = JSON.parse(await data.text())?.detail; } catch { /* not JSON */ }
  }
  if (status === 429) return `Report limit reached (${typeof detail === 'string' ? detail : 'too many requests'}).`;
  if (status === 403) return typeof detail === 'string' ? detail : 'Access denied for this dataset.';
  if (err?.code === 'ECONNABORTED') return `The ${what} took too long. Please try again.`;
  if (typeof detail === 'string' && detail) return detail;
  return `Could not create the ${what}. Please ensure the server is running.`;
};

export const ReportPage: React.FC = () => {
  const { isOlist, activeDatasetId, activeDataset, activeReady } = useActiveDataset();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const datasetKey = isOlist ? null : activeDatasetId;
  const { toast, fmtMeasure, measureCurrency, currency } = useUi();
  const [elapsed, setElapsed] = useState(0);
  const [revealed, setRevealed] = useState(99);
  useEffect(() => {
    if (!loading) return;
    const started = Date.now();
    setElapsed(0);
    const t = window.setInterval(() => setElapsed((Date.now() - started) / 1000), 250);
    return () => window.clearInterval(t);
  }, [loading]);

  // Uploaded datasets: the server formats numbers without a currency; re-format money measures with the picked one.
  const useCur = !!report && !report.is_demo && !!currency;
  const money = (display: string, value: number | null | undefined, measureName: string, aggregation = 'SUM') => {
    if (!useCur) return display;
    const v = value ?? parseDisplayNumber(display);
    return measureCurrency({ name: measureName, aggregation }) && v !== null ? fmtMeasure(v, { name: measureName, aggregation }) : display;
  };
  const sentence = (t: string, measureName: string) => (useCur && measureCurrency({ name: measureName, aggregation: 'SUM' }) ? currencyizeSentence(t, currency) : t);

  // Dataset switched: drop the old preview and ignore any in-flight response. Only on a real change of id
  // (not on StrictMode's simulated remount, which would otherwise discard the one auto-generated request).
  const shownFor = useRef(activeDatasetId);
  useEffect(() => {
    if (shownFor.current === activeDatasetId) return;
    shownFor.current = activeDatasetId;
    latest.current += 1;
    setReport(null);
    setError(null);
    setLoading(false);
  }, [activeDatasetId]);

  const generate = async () => {
    const reqId = ++latest.current;
    setLoading(true);
    setError(null);
    try {
      const r = await api.getReport(datasetKey);
      if (latest.current === reqId) {
        setReport(r);
        setRevealed(0);
        const failed = Object.keys(r.section_errors || {}).length;
        toast(failed ? 'info' : 'success', 'Report ready',
          failed ? `${failed} section(s) unavailable; the rest is complete.` : `Built in ${r.elapsed_seconds.toFixed(1)} s${r.cached ? ' (cached)' : ''}.`);
      }
    } catch (err: any) {
      const msg = await errorText(err, 'report');
      if (latest.current === reqId) { setError(msg); toast('error', 'Report failed', msg); }
    } finally {
      if (latest.current === reqId) setLoading(false);
    }
  };

  const download = async () => {
    setDownloading(true);
    setError(null);
    try {
      const { blob, filename } = await api.downloadReportPdf(datasetKey);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      toast('success', 'PDF downloaded', filename);
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (err: any) {
      const msg = await errorText(err, 'PDF');
      setError(msg);
      toast('error', 'PDF download failed', msg);
    } finally {
      setDownloading(false);
    }
  };

  // "Generate report" buttons elsewhere link to /report?autogen=1. The ref makes it fire exactly once
  // (React StrictMode runs effects twice in development; each report counts against the 10/hour limit).
  const autogenDone = useRef(false);
  useEffect(() => {
    if (params.get('autogen') === '1' && activeReady && !autogenDone.current) {
      autogenDone.current = true;
      setParams({}, { replace: true });
      generate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, activeReady]);

  const E = report?.section_errors || {};
  const name = isOlist ? 'Olist demo' : activeDataset?.name || 'dataset';
  const compact = (v: number) => {
    const body = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(v);
    return report?.currency ? `${report.currency} ${body}` : body;
  };

  return (
    <div className="space-y-5 pb-12">
      <div className="flex flex-wrap items-center justify-between gap-3 bg-white border border-slate-200/80 rounded-2xl p-4">
        <div className="min-w-0">
          <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2"><FileText className="w-4 h-4 text-indigo-600" />Report</h2>
          <p className="text-xs text-slate-500">
            One-click report for {name} · fixed templates, no AI
            {report ? ` · built in ${report.elapsed_seconds.toFixed(1)} s${report.cached ? ' (cached)' : ''}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={generate} disabled={loading || !activeReady}
            className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 cursor-pointer disabled:opacity-60">
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            {report ? 'Regenerate' : 'Generate report'}
          </button>
          <button onClick={download} disabled={!report || downloading}
            className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg text-xs font-semibold flex items-center gap-1.5 cursor-pointer disabled:opacity-50">
            {downloading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
            Download PDF
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 text-rose-800 text-xs p-3 flex gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />{error}
        </div>
      )}

      {!report && !loading && !error && (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center">
          <FileText className="w-8 h-8 text-slate-300 mx-auto mb-2" />
          <div className="text-sm font-semibold text-slate-700">Create a report for {name}</div>
          <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
            Summary, KPIs, monthly trend, breakdowns, top anomalies with their drivers, a 3-month forecast and data-quality checks,
            on screen and as a PDF. Limited to a few reports per hour.
          </p>
        </div>
      )}

      {loading && (
        <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-soft animate-fade-in-up" aria-live="polite" aria-busy="true">
          <div className="flex items-center justify-between gap-3 mb-3">
            <div className="text-sm font-semibold text-slate-800">Building the report…</div>
            <div className="text-[11px] text-slate-500 tabular-nums">{elapsed.toFixed(0)} s / 45 s budget</div>
          </div>
          <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden mb-4">
            <div className="h-full rounded-full bg-brand-gradient transition-all duration-300" style={{ width: `${Math.min(100, (elapsed / 45) * 100)}%` }} />
          </div>
          <ol className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {REPORT_STEPS.map((st) => (
              <li key={st.key} className="flex items-center gap-2 text-xs text-slate-600">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-500 shrink-0" />{st.label}
              </li>
            ))}
          </ol>
          <p className="mt-3 text-[11px] text-slate-400">All sections run in parallel on the server; each one is marked done or unavailable when the report arrives.</p>
        </div>
      )}
      {report && !loading && revealed < REPORT_STEPS.length + 1 && (
        <StepReveal report={report} onDone={() => setRevealed(99)} />
      )}

      {report && !loading && (
        <div className="bg-white border border-slate-200/80 rounded-2xl p-4 sm:p-6 space-y-6 shadow-soft animate-fade-in-up min-w-0">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-indigo-600">InsightForge report</div>
            <h1 className="text-xl font-extrabold text-slate-900">{report.dataset_name}</h1>
            <div className="text-xs text-slate-500">
              Generated {new Date(report.generated_at).toLocaleString()} · Period: {report.period || 'no time column'}
              {report.total_rows != null ? ` · ${report.total_rows.toLocaleString()} rows in ${Object.keys(report.row_counts).length} tables` : ''}
            </div>
            {Object.keys(report.row_counts).length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {Object.entries(report.row_counts).map(([t, n]) => (
                  <span key={t} className="text-[10px] bg-slate-100 text-slate-600 rounded px-1.5 py-0.5">{t}: {n.toLocaleString()}</span>
                ))}
              </div>
            )}
          </div>

          <Section title="Executive summary" reason={!report.summary ? E.summary : undefined}>
            <ul className="list-disc pl-5 space-y-1 text-xs text-slate-700">{report.summary?.map((s) => <li key={s}>{s}</li>)}</ul>
          </Section>

          <Section title="Key figures" reason={!report.kpis ? E.kpis : undefined}>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 stagger">
              {report.kpis?.map((k) => (
                <div key={k.label} className="border border-slate-200 rounded-xl p-3 min-w-0 card-lift">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">{k.label}</div>
                  <div className="text-sm font-bold text-slate-900 font-mono truncate" title={money(k.display, k.value, k.label)}>{money(k.display, k.value, k.label)}</div>
                </div>
              ))}
            </div>
          </Section>

          <Section title="Monthly trend" reason={!report.trend ? E.trend : undefined}>
            {report.trend && (
              <>
                <div className="text-[11px] text-slate-500 mb-1">{report.trend.title}</div>
                <div className="h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={report.trend.points} margin={{ top: 4, right: 8, left: 8, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                      <XAxis dataKey="period" tick={{ fontSize: 10, fill: '#64748b' }} minTickGap={16} />
                      <YAxis tick={{ fontSize: 10, fill: '#64748b' }} width={70} tickFormatter={compact} />
                      <Tooltip formatter={(v: any) => compact(Number(v))} contentStyle={{ fontSize: 11 }} />
                      <Area dataKey="value" name="Value" stroke="#4f46e5" fill="#6366f1" fillOpacity={0.1} isAnimationActive={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </>
            )}
          </Section>

          <Section title="Top breakdowns" reason={!report.breakdowns ? E.breakdowns : undefined}>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {report.breakdowns?.map((b) => (
                <div key={b.title}>
                  <div className="text-xs font-semibold text-slate-800 mb-1">{b.title}</div>
                  <table className="w-full text-left text-[11px]">
                    <tbody>
                      {b.items.map((i) => (
                        <tr key={i.label} className="border-b border-slate-100">
                          <td className="py-1 pr-2 text-slate-700">{i.label}</td>
                          <td className="py-1 pr-2 text-right font-mono whitespace-nowrap">{money(i.display, i.value, b.title.split(' by ')[0])}</td>
                          <td className="py-1 text-right text-slate-500 w-14">{i.share_pct != null ? `${i.share_pct.toFixed(1)}%` : ''}</td>
                        </tr>
                      ))}
                      {b.other_groups > 0 && b.other_display && (
                        <tr className="border-b border-slate-100 text-slate-500">
                          <td className="py-1 pr-2">All other ({b.other_groups} groups)</td><td className="py-1 pr-2 text-right font-mono whitespace-nowrap">{money(b.other_display, null, b.title.split(' by ')[0])}</td><td />
                        </tr>
                      )}
                    </tbody>
                  </table>
                  {b.total_line && <div className="text-[10px] text-slate-600 mt-1">{useCur && b.total_value != null && measureCurrency({ name: b.title.split(' by ')[0], aggregation: 'SUM' }) ? `All groups total: ${fmtMeasure(b.total_value, { name: b.title.split(' by ')[0], aggregation: 'SUM' })}` : b.total_line}</div>}
                </div>
              ))}
            </div>
          </Section>

          <Section title="Top anomalies and their drivers" reason={!report.anomalies ? E.anomalies : undefined}>
            {report.anomalies && report.anomalies.length === 0 && <div className="text-xs text-slate-500">No anomalies were flagged.</div>}
            {report.anomalies && report.anomalies.length > 0 && (
              <>
                <div className="text-[11px] text-slate-500 mb-1">{report.anomaly_count} anomalies flagged; the {report.anomalies.length} largest:</div>
                <div className="overflow-x-auto"><table className="w-full text-left text-[11px] min-w-[36rem]">
                  <thead className="text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-200">
                    <tr><th className="py-1 pr-2">Date</th><th className="py-1 pr-2">Change</th><th className="py-1 pr-2">Observed vs expected</th><th className="py-1">Main driver</th></tr>
                  </thead>
                  <tbody>
                    {report.anomalies.map((a) => (
                      <tr key={a.period} className="border-b border-slate-100 align-top">
                        <td className="py-1 pr-2 font-mono">{a.period}</td>
                        <td className={`py-1 pr-2 ${a.direction === 'spike' ? 'text-emerald-700' : 'text-rose-700'}`}>{a.direction} ({a.severity})</td>
                        <td className="py-1 pr-2 font-mono whitespace-nowrap">{money(a.observed_display, null, a.metric_label)} vs {money(a.expected_display, null, a.metric_label)}</td>
                        <td className="py-1 text-slate-700 min-w-[12rem]">{sentence(a.driver_sentence, a.metric_label)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table></div>
              </>
            )}
          </Section>

          <Section title="3-month baseline forecast" reason={!report.forecast ? E.forecast : undefined}>
            {report.forecast && (report.forecast.status === 'ok' ? (
              <>
                <div className="text-xs text-slate-700 mb-2">
                  {report.forecast.metric_label}: reliability <b>{report.forecast.reliability}</b> (backtest MAPE {report.forecast.mape?.toFixed(1)}% vs naive {report.forecast.naive_mape?.toFixed(1)}%) · {report.forecast.training_window}
                </div>
                <table className="w-full text-left text-[11px] max-w-xl">
                  <tbody>
                    {report.forecast.points.map((p) => (
                      <tr key={p.period} className="border-b border-slate-100">
                        <td className="py-1 pr-2 font-mono">{p.period}</td>
                        <td className="py-1 pr-2 font-mono font-semibold whitespace-nowrap">{money(p.expected_display, p.expected, report.forecast!.metric_label)}</td>
                        <td className="py-1 text-slate-500">80% range {useCur ? `${money('', p.lower_80, report.forecast!.metric_label)} to ${money('', p.upper_80, report.forecast!.metric_label)}` : p.range_display}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            ) : (
              <div className="text-xs text-amber-800">No forecast for {report.forecast.metric_label}: {report.forecast.reason}</div>
            ))}
            {report.forecast && <div className="text-[10px] text-slate-500 mt-1">{report.forecast.disclaimer}</div>}
          </Section>

          <Section title="Data quality" reason={!report.data_quality ? E.data_quality : undefined}>
            <div className="overflow-x-auto">
            <table className="w-full text-left text-[11px] min-w-[26rem]">
              <tbody>
                {report.data_quality?.map((d) => (
                  <tr key={d.check} className="border-b border-slate-100 align-top">
                    <td className="py-1 pr-2 text-slate-700">{d.check}</td>
                    <td className="py-1 pr-2"><span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${STATUS_CHIP[d.status] || ''}`}>{d.status}</span></td>
                    <td className="py-1 text-slate-500">{d.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </Section>

          <Section title="Caveats">
            <ul className="list-disc pl-5 space-y-0.5 text-[11px] text-slate-600">{report.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
          </Section>
          <Section title="Methodology">
            <ul className="list-disc pl-5 space-y-0.5 text-[11px] text-slate-600">{report.methodology.map((m) => <li key={m}>{m}</li>)}</ul>
          </Section>
          <div className="text-right">
            <button onClick={() => navigate('/anomalies')} className="text-[11px] text-indigo-600 hover:underline cursor-pointer">Open the Anomalies page →</button>
          </div>
        </div>
      )}
    </div>
  );
};

const Section: React.FC<{ title: string; reason?: string; children?: React.ReactNode }> = ({ title, reason, children }) => (
  <section>
    <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-700 mb-2">{title}</h3>
    {reason ? (
      <div className="rounded-lg border border-amber-200 bg-amber-50 text-amber-800 text-xs px-3 py-2">Section unavailable: {reason}</div>
    ) : children}
  </section>
);

export default ReportPage;

const REPORT_STEPS: { key: string; label: string }[] = [
  { key: 'kpis', label: 'Key figures' },
  { key: 'trend', label: 'Monthly trend' },
  { key: 'breakdowns', label: 'Top breakdowns' },
  { key: 'anomalies', label: 'Anomalies and their drivers' },
  { key: 'forecast', label: '3-month forecast' },
  { key: 'data_quality', label: 'Data-quality checks' },
  { key: 'summary', label: 'Executive summary' },
];

/** After the report arrives: tick each section off one by one (done, or unavailable with its reason). */
const StepReveal: React.FC<{ report: ReportResponse; onDone: () => void }> = ({ report, onDone }) => {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (n >= REPORT_STEPS.length) { const t = window.setTimeout(onDone, 900); return () => window.clearTimeout(t); }
    const t = window.setTimeout(() => setN((x) => x + 1), 110);
    return () => window.clearTimeout(t);
  }, [n, onDone]);
  return (
    <ol className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 bg-white border border-slate-200/80 rounded-2xl p-4 shadow-xs" aria-label="Report sections">
      {REPORT_STEPS.map((st, i) => {
        const err = report.section_errors?.[st.key];
        const shown = i < n;
        return (
          <li key={st.key} className={`flex items-center gap-2 text-xs transition-opacity ${shown ? 'opacity-100' : 'opacity-40'}`}>
            {!shown ? <CircleDashed className="w-3.5 h-3.5 text-slate-300 shrink-0" />
              : err ? <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0 animate-pop" />
              : <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0 animate-pop" />}
            <span className={`truncate ${err && shown ? 'text-amber-700' : 'text-slate-700'}`} title={err || st.label}>{st.label}</span>
          </li>
        );
      })}
    </ol>
  );
};
