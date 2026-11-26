import React, { useEffect, useRef, useState } from 'react';
import { AlertOctagon, Play } from 'lucide-react';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../../services/api';
import { useActiveDataset } from '../../contexts/ActiveDatasetContext';
import { WorkspaceAnomalyScanResponse } from '../../types/api';
import { AnomalyExplainDrawer, ExplainButton, ExplainTarget } from '../AnomalyExplainDrawer';
import { InfoTip } from '../ui';
import { useUi } from '../../contexts/UiContext';
import { ChartSkeleton, ErrorBanner, KpiSkeleton, PageHeader, apiErrorMessage, useWorkspaceData } from './shared';

type Grain = 'daily' | 'weekly';
type Severity = 'all' | 'high' | 'medium' | 'low';

// Same marker colours as the Olist Anomalies page.
const SEV_COLOR: Record<string, string> = { high: '#ef4444', medium: '#f59e0b', low: '#3b82f6' };
const SEV_CHIP: Record<string, string> = {
  high: 'bg-rose-100 text-rose-800',
  medium: 'bg-amber-100 text-amber-800',
  low: 'bg-blue-100 text-blue-800',
};
const METHOD_LABEL: Record<string, string> = {
  rolling_zscore: 'Rolling MAD z-score',
  stl_residual: 'STL residual',
  isolation_forest: 'IsolationForest',
  iqr_dimension: 'IQR slices',
};

const renderDot = (props: any): React.ReactElement<SVGElement> => {
  const { cx, cy, payload, index } = props;
  if (!payload || !payload.is_anomaly) return <circle key={`n-${index}`} cx={cx} cy={cy} r={0} opacity={0} />;
  return <circle key={`d-${payload.period || index}`} cx={cx} cy={cy} r={5} fill={SEV_COLOR[payload.severity] || '#f59e0b'} stroke="#fff" strokeWidth={2} />;
};

/** Anomalies for an uploaded dataset (the Olist Anomalies page is untouched and used for the demo). */
export const CustomAnomalies: React.FC = () => {
  const { activeDatasetId, activeDataset } = useActiveDataset();
  const [metric, setMetric] = useState<string | null>(null);
  const [grain, setGrain] = useState<Grain>('daily');
  const [severity, setSeverity] = useState<Severity>('all');
  const [scan, setScan] = useState<WorkspaceAnomalyScanResponse | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [explainTarget, setExplainTarget] = useState<ExplainTarget | null>(null);
  // Latest active dataset, read when a (slow) scan returns: results for another dataset are dropped.
  const activeIdRef = useRef(activeDatasetId);
  activeIdRef.current = activeDatasetId;

  useEffect(() => {
    setMetric(null);
    setGrain('daily');
    setSeverity('all');
    setScan(null);
    setScanError(null);
    setExplainTarget(null);
  }, [activeDatasetId]);

  const { data, loading, error, reload } = useWorkspaceData(
    `anomalies:${activeDatasetId}:${metric ?? ''}:${grain}:${severity}`,
    () => api.getDatasetAnomalies(activeDatasetId, { metric, grain, severity: severity === 'all' ? null : severity }),
    'anomalies'
  );

  const runScan = async () => {
    const id = activeDatasetId;
    setScanning(true);
    setScanError(null);
    try {
      const res = await api.scanDatasetAnomalies(id, grain);
      if (id === activeIdRef.current) setScan(res);
    } catch (err: any) {
      if (id === activeIdRef.current) setScanError(apiErrorMessage(err, 'the anomaly scan'));
    } finally {
      setScanning(false);
    }
  };

  const items = data?.anomalies || [];
  const metricOpt = data?.metrics.find((m) => m.key === data.metric);
  const metricLabel = metricOpt?.label || data?.metric || '';
  const { fmtMeasure, fmtMeasureCompact } = useUi();
  const measure = { name: metricOpt?.label, column: metricOpt?.column, aggregation: metricOpt?.aggregation };
  const fm = (v: number | null | undefined) => fmtMeasure(v, measure);
  const counts = { high: 0, medium: 0, low: 0 } as Record<string, number>;
  items.forEach((a) => (counts[a.severity] = (counts[a.severity] || 0) + 1));
  const candidates = items.filter((a) => a.known_event_candidate).length;

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        icon={<AlertOctagon className="w-4 h-4 text-indigo-600" />}
        title={`Anomalies: ${activeDataset?.name || 'Uploaded dataset'}`}
        subtitle="Deterministic detection on your own time series (MAD z-score, STL, IQR slices, IsolationForest), same calibration as the Olist demo."
        loading={loading}
        cached={data?.cached}
        onRefresh={reload}
      >
        <button
          onClick={runScan}
          disabled={scanning}
          className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 cursor-pointer disabled:opacity-60"
        >
          <Play className="w-3.5 h-3.5" />
          {scanning ? 'Scanning…' : 'Scan all measures'}
        </button>
      </PageHeader>

      <div className="flex flex-wrap items-center gap-3 bg-white border border-slate-200/80 rounded-2xl p-3 shadow-xs text-xs">
        <label className="flex items-center gap-1.5 text-slate-600">
          Metric
          <select
            aria-label="Anomaly metric"
            value={data?.metric ?? metric ?? ''}
            disabled={!data || data.metrics.length === 0}
            onChange={(e) => setMetric(e.target.value)}
            className="bg-white border border-slate-200 rounded-lg font-semibold text-slate-700 px-2 py-1.5 max-w-[240px]"
          >
            {!data && <option value="">Loading…</option>}
            {data?.metrics.map((m) => (
              <option key={m.key} value={m.key}>{m.column ? `${m.label} (${m.aggregation})` : m.label}</option>
            ))}
          </select>
        </label>
        <div className="flex rounded-lg border border-slate-200 overflow-hidden" role="group" aria-label="Grain">
          {(['daily', 'weekly'] as Grain[]).map((g) => (
            <button key={g} onClick={() => setGrain(g)} aria-pressed={grain === g}
              className={`px-2.5 py-1.5 font-semibold cursor-pointer capitalize ${grain === g ? 'bg-indigo-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'}`}>
              {g}
            </button>
          ))}
        </div>
        <div className="flex rounded-lg border border-slate-200 overflow-hidden" role="group" aria-label="Severity">
          {(['all', 'high', 'medium', 'low'] as Severity[]).map((s) => (
            <button key={s} onClick={() => setSeverity(s)} aria-pressed={severity === s}
              className={`px-2.5 py-1.5 font-semibold cursor-pointer uppercase ${severity === s ? 'bg-slate-800 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'}`}>
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500 -mt-2">
        <span className="inline-flex items-center gap-1">MAD z-score <InfoTip term="MAD" /></span>
        <span className="inline-flex items-center gap-1">STL <InfoTip term="STL" /></span>
        <span className="inline-flex items-center gap-1">IQR slices <InfoTip term="IQR" /></span>
      </div>
      {error && <ErrorBanner message={error} />}
      {scanError && <ErrorBanner message={scanError} />}
      {scan && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-900 flex items-center justify-between">
          <span>
            <strong>Scan complete:</strong> {scan.scanned_metrics.length} measures, {scan.anomalies_detected} anomalies ({scan.high_severity_count} high severity).
          </span>
          <button onClick={() => setScan(null)} className="font-bold hover:underline cursor-pointer">Dismiss</button>
        </div>
      )}

      {!data && loading && (
        <>
          <KpiSkeleton count={4} />
          <ChartSkeleton height="h-80" />
        </>
      )}

      {data && (
        <>
          {data.section_errors.anomalies && <ErrorBanner message={data.section_errors.anomalies} />}
          {data.notes.length > 0 && (
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-[11px] text-slate-600 space-y-1">
              {data.notes.map((n, i) => <div key={i}>• {n}</div>)}
            </div>
          )}

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-white border border-slate-200/80 rounded-2xl p-4 shadow-xs">
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Anomalies</div>
              <div className="text-2xl font-extrabold text-slate-900 mt-1">{data.total_anomalies}</div>
              <div className="text-[10px] text-slate-400">{severity === 'all' ? 'all severities' : `${severity} only`}</div>
            </div>
            <div className="bg-white border border-slate-200/80 rounded-2xl p-4 shadow-xs">
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">High severity</div>
              <div className="text-2xl font-extrabold text-rose-600 mt-1">{counts.high}</div>
              <div className="text-[10px] text-slate-400">{counts.medium} medium · {counts.low} low</div>
            </div>
            <div className="bg-white border border-slate-200/80 rounded-2xl p-4 shadow-xs">
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Known-event candidates</div>
              <div className="text-2xl font-extrabold text-emerald-600 mt-1">{candidates}</div>
              <div className="text-[10px] text-slate-400">generic calendar, labels only</div>
            </div>
            <div className="bg-white border border-slate-200/80 rounded-2xl p-4 shadow-xs">
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Methods run</div>
              <div className="text-[11px] font-semibold text-slate-700 mt-1.5 leading-snug">
                {data.methods_run.map((m) => METHOD_LABEL[m] || m).join(', ') || 'none'}
              </div>
            </div>
          </div>

          <section className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
            <h3 className="text-xs font-bold text-slate-900 mb-3">
              {metricLabel} ({grain}) with expected baseline; dots mark anomalies
            </h3>
            {data.time_series.length > 0 ? (
              <div className="h-80 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.time_series} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="period" fontSize={9} stroke="#94a3b8" minTickGap={24} />
                    <YAxis fontSize={10} stroke="#94a3b8" width={64} tickFormatter={(v) => fmtMeasureCompact(Number(v), measure)} />
                    <Tooltip formatter={(v) => fm(Number(v))} />
                    <Legend wrapperStyle={{ fontSize: 10 }} />
                    <Line type="monotone" dataKey="observed" name="Observed" stroke="#4f46e5" strokeWidth={1.5} dot={renderDot} isAnimationActive={false} />
                    <Line type="monotone" dataKey="expected" name="Expected (rolling median)" stroke="#94a3b8" strokeDasharray="4 4" dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="h-40 flex items-center justify-center text-xs text-slate-400">No time series available.</div>
            )}
          </section>

          <section className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-3">Anomalies log ({items.length})</div>
            {items.length === 0 ? (
              <div className="text-xs text-slate-500 py-4 text-center">No anomalies for this selection.</div>
            ) : (
              <div className="overflow-x-auto max-h-[28rem] overflow-y-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-[10px] text-slate-500 uppercase tracking-wider border-b border-slate-200 sticky top-0 bg-white">
                    <tr>
                      <th className="py-2 pr-3">Period</th>
                      <th className="py-2 pr-3">Method</th>
                      <th className="py-2 pr-3 text-right">Observed</th>
                      <th className="py-2 pr-3 text-right">Expected</th>
                      <th className="py-2 pr-3 text-right">Dev. score</th>
                      <th className="py-2 pr-3">Direction</th>
                      <th className="py-2 pr-3">Severity</th>
                      <th className="py-2 pr-3">Known-event candidate</th>
                      <th className="py-2">Why?</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((a, i) => (
                      <tr key={`${a.metric}-${a.period}-${a.method}-${i}`} className="border-b border-slate-100">
                        <td className="py-1.5 pr-3 font-mono">{a.period}</td>
                        <td className="py-1.5 pr-3 text-slate-500">{METHOD_LABEL[a.method] || a.method}</td>
                        <td className="py-1.5 pr-3 text-right font-semibold tabular-nums">{fm(a.observed)}</td>
                        <td className="py-1.5 pr-3 text-right text-slate-500 tabular-nums">{fm(a.expected)}</td>
                        <td className="py-1.5 pr-3 text-right">{a.deviation_score.toFixed(2)}</td>
                        <td className={`py-1.5 pr-3 capitalize ${a.direction === 'spike' ? 'text-emerald-700' : 'text-rose-700'}`}>{a.direction}</td>
                        <td className="py-1.5 pr-3">
                          <span className={`px-1.5 py-0.5 rounded font-semibold uppercase text-[10px] ${SEV_CHIP[a.severity]}`}>{a.severity}</span>
                        </td>
                        <td className="py-1.5 pr-3 text-emerald-700">{a.known_event_candidate || '—'}</td>
                        <td className="py-1.5">
                          {a.dimension === 'overall' && (
                            <ExplainButton compact onClick={() => setExplainTarget({
                              source: { kind: 'dataset', datasetId: activeDatasetId },
                              metric: data?.metric ?? metric, period: a.period, grain,
                            })} />
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {data.slice_outliers.length > 0 && (
            <section className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
              <div className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-3 flex items-center gap-1">Slice outliers (IQR across groups) <InfoTip term="IQR" /></div>
              <div className="overflow-x-auto -mx-1 px-1">
              <table className="w-full text-left text-xs min-w-[28rem]">
                <tbody>
                  {data.slice_outliers.map((s, i) => (
                    <tr key={i} className="border-b border-slate-100">
                      <td className="py-1.5 pr-3 font-mono">{s.dimension}</td>
                      <td className="py-1.5 pr-3 text-right font-semibold tabular-nums">{fm(s.observed)}</td>
                      <td className="py-1.5 pr-3 text-right text-slate-500 tabular-nums">median {fm(s.expected)}</td>
                      <td className="py-1.5 pr-3 capitalize">{s.direction}</td>
                      <td className="py-1.5"><span className={`px-1.5 py-0.5 rounded font-semibold uppercase text-[10px] ${SEV_CHIP[s.severity]}`}>{s.severity}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </section>
          )}
        </>
      )}
      <AnomalyExplainDrawer target={explainTarget} onClose={() => setExplainTarget(null)} />
    </div>
  );
};
