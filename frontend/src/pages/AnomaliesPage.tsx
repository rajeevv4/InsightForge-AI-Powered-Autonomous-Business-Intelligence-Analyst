import { formatCompact, formatMoney } from '../lib/format';
import React, { useEffect, useState, useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  AlertTriangle,
  Flame,
  TrendingDown,
  TrendingUp,
  Activity,
  Calendar,
  Filter,
  RefreshCw,
  Search,
  CheckCircle,
  HelpCircle
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend
} from 'recharts';
import { api } from '../services/api';
import { AnomalyItem, AnomalyListResponse, AnomalyScanResponse } from '../types/api';
import { ErrorBanner } from '../components/ErrorBanner';
import { AnomalyExplainDrawer, ExplainButton, ExplainTarget } from '../components/AnomalyExplainDrawer';
import { InfoTip } from '../components/ui';
import { useUi } from '../contexts/UiContext';

export const AnomaliesPage: React.FC = () => {
  const outletContext = useOutletContext<{ refreshTrigger?: number }>();

  // Filter states
  const [metric, setMetric] = useState<string>('gross_revenue');
  const [grain, setGrain] = useState<'daily' | 'weekly'>('daily');
  const [severity, setSeverity] = useState<string>('all');

  // Data states
  const [anomalyData, setAnomalyData] = useState<AnomalyListResponse | null>(null);
  const [scanResult, setScanResult] = useState<AnomalyScanResponse | null>(null);
  const [explainTarget, setExplainTarget] = useState<ExplainTarget | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [scanning, setScanning] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const loadAnomalies = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getAnomalies(metric, grain, severity);
      setAnomalyData(data);
    } catch (err: any) {
      console.error('Failed to load anomalies:', err);
      const msg = err?.response?.status === 503
        ? 'Database unavailable: The database server is currently disconnected.'
        : 'Failed to load statistical anomalies from the server.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [metric, grain, severity]);

  useEffect(() => {
    loadAnomalies();
  }, [loadAnomalies, outletContext?.refreshTrigger]);

  const { toast } = useUi();
  const handleRunScan = async () => {
    setScanning(true);
    try {
      const res = await api.scanAnomalies({ grain });
      setScanResult(res);
      toast('success', 'Scan complete', `${res.anomalies_detected ?? 0} anomalies (${res.high_severity_count ?? 0} high severity).`);
      await loadAnomalies();
    } catch (err: any) {
      console.error('Anomaly scan failed:', err);
      const msg = err?.response?.status === 429
        ? 'Rate limit exceeded: Too many scan requests. Please wait a minute.'
        : (err?.response?.status === 503
          ? 'Database unavailable: Cannot run scan without an active database connection.'
          : 'Failed to complete full anomaly scan.');
      toast('error', 'Scan failed', msg);
      alert(msg);
    } finally {
      setScanning(false);
    }
  };

  const formatValue = (val: number, met: string) => {
    if (met === 'gross_revenue' || met === 'aov') {
      return formatMoney(val, 'R$');
    }
    if (met === 'on_time_delivery_rate') {
      return `${val.toFixed(1)}%`;
    }
    if (met === 'avg_review_score') {
      return `${val.toFixed(2)} ★`;
    }
    return Math.round(val).toLocaleString();
  };

  const metricOptions = [
    { id: 'gross_revenue', label: 'Gross Revenue' },
    { id: 'order_count', label: 'Delivered Orders' },
    { id: 'aov', label: 'Average Order Value (AOV)' },
    { id: 'on_time_delivery_rate', label: 'On-Time Delivery Rate (%)' },
    { id: 'avg_review_score', label: 'Customer Review CSAT' },
  ];

  // Custom Chart Dot to highlight anomalies
  const renderCustomDot = (props: any): React.ReactElement<SVGElement> => {
    const { cx, cy, payload, index } = props;
    if (!payload || !payload.is_anomaly) {
      return <circle key={`dot-none-${index}`} cx={cx} cy={cy} r={0} opacity={0} />;
    }

    let fillColor = '#f59e0b'; // amber medium
    if (payload.severity === 'high') fillColor = '#ef4444'; // red high
    if (payload.severity === 'low') fillColor = '#3b82f6'; // blue low

    return (
      <circle
        key={`dot-${payload.period || index}`}
        cx={cx}
        cy={cy}
        r={5}
        fill={fillColor}
        stroke="#ffffff"
        strokeWidth={2}
      />
    );
  };

  // Filtered anomalies table
  const displayedAnomalies = anomalyData?.anomalies || [];
  const highCount = displayedAnomalies.filter((a) => a.severity === 'high').length;
  const knownEventsCount = displayedAnomalies.filter((a) => !!a.known_event_candidate).length;

  return (
    <div className="space-y-8 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200/80 pb-4">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
            <Activity className="w-6 h-6 text-indigo-600" />
            Statistical Anomalies & Outliers
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Deterministic time-series outlier detection (Robust Z-Score, STL Residuals, IQR, IsolationForest).
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={handleRunScan}
            disabled={scanning}
            className="flex items-center space-x-2 px-3.5 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white rounded-lg text-xs font-semibold shadow-xs transition cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${scanning ? 'animate-spin' : ''}`} />
            <span>{scanning ? 'Scanning...' : 'Run Full Anomaly Scan'}</span>
          </button>
        </div>
      </div>

      {error ? (
        <ErrorBanner
          title="Unable to load anomaly detection"
          message={error}
          onRetry={loadAnomalies}
        />
      ) : null}

      {scanResult && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center justify-between text-xs text-emerald-900">
          <div className="flex items-center space-x-2">
            <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>
              <strong>Scan Complete:</strong> Analyzed {scanResult.scanned_metrics?.length ?? 0} metrics ({grain}). Detected {scanResult.anomalies_detected ?? 0} total anomalies ({scanResult.high_severity_count ?? 0} high severity).
            </span>
          </div>
          <button
            onClick={() => setScanResult(null)}
            className="text-emerald-700 font-bold hover:underline cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* KPI Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Total Anomalies</span>
            <Activity className="w-4 h-4 text-indigo-500" />
          </div>
          <div className="mt-2 flex items-baseline">
            <span className="text-2xl font-bold text-slate-900">
              {loading ? '...' : (anomalyData?.total_anomalies || 0)}
            </span>
            <span className="ml-2 text-2xs text-slate-500 font-medium">in current view</span>
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">High Severity</span>
            <Flame className="w-4 h-4 text-rose-500" />
          </div>
          <div className="mt-2 flex items-baseline">
            <span className="text-2xl font-bold text-rose-600">
              {loading ? '...' : highCount}
            </span>
            <span className="ml-2 text-2xs text-rose-500 font-medium">requiring review</span>
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Known Events</span>
            <Calendar className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="mt-2 flex items-baseline">
            <span className="text-2xl font-bold text-emerald-600">
              {loading ? '...' : knownEventsCount}
            </span>
            <span className="ml-2 text-2xs text-emerald-600 font-medium">e.g. Black Friday</span>
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Detection Logic</span>
            <HelpCircle className="w-4 h-4 text-slate-400" />
          </div>
          <div className="mt-2">
            <span className="text-xs font-semibold text-slate-700">Deterministic ML</span>
            <p className="text-2xs text-slate-400 mt-0.5 flex flex-wrap items-center gap-x-1.5">STL <InfoTip term="STL" /> · MAD Z-Score <InfoTip term="MAD" /> · IQR <InfoTip term="IQR" /> · IF</p>
          </div>
        </div>
      </div>

      {/* Control Bar: Metric, Grain, Severity */}
      <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs flex flex-wrap items-center justify-between gap-4">
        {/* Metric Selector */}
        <div className="flex items-center space-x-2">
          <span className="text-xs font-semibold text-slate-700">Metric:</span>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
            className="text-xs bg-slate-50 border border-slate-300 rounded-lg px-3 py-1.5 font-medium text-slate-800 focus:outline-indigo-500"
          >
            {metricOptions.map((opt) => (
              <option key={opt.id} value={opt.id}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Grain Toggle */}
        <div className="flex items-center space-x-1 bg-slate-100 p-1 rounded-lg">
          <button
            onClick={() => setGrain('daily')}
            className={`px-3 py-1 text-xs font-semibold rounded-md transition cursor-pointer ${
              grain === 'daily'
                ? 'bg-white text-indigo-600 shadow-2xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Daily
          </button>
          <button
            onClick={() => setGrain('weekly')}
            className={`px-3 py-1 text-xs font-semibold rounded-md transition cursor-pointer ${
              grain === 'weekly'
                ? 'bg-white text-indigo-600 shadow-2xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Weekly
          </button>
        </div>

        {/* Severity Filter */}
        <div className="flex items-center space-x-2">
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <span className="text-xs font-semibold text-slate-700">Severity:</span>
          <div className="flex items-center space-x-1 bg-slate-100 p-1 rounded-lg">
            {['all', 'high', 'medium', 'low'].map((s) => (
              <button
                key={s}
                onClick={() => setSeverity(s)}
                className={`px-2.5 py-1 text-2xs font-bold uppercase rounded-md transition cursor-pointer ${
                  severity === s
                    ? 'bg-white text-slate-900 shadow-2xs'
                    : 'text-slate-500 hover:text-slate-900'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Time Series Chart with Anomaly Highlights */}
      <div className="bg-white p-6 rounded-xl border border-slate-200/80 shadow-2xs">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-sm font-bold text-slate-900">
              {metricOptions.find((m) => m.id === metric)?.label || metric} Time Series
            </h2>
            <p className="text-2xs text-slate-500">
              Solid line indicates observed values; dashed line shows expected baseline. Dots highlight detected anomalies.
            </p>
          </div>
          <div className="flex items-center space-x-3 text-2xs text-slate-500">
            <span className="flex items-center space-x-1">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block" />
              <span>High Severity</span>
            </span>
            <span className="flex items-center space-x-1">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" />
              <span>Medium</span>
            </span>
            <span className="flex items-center space-x-1">
              <span className="w-2.5 h-2.5 rounded-full bg-blue-500 inline-block" />
              <span>Low</span>
            </span>
          </div>
        </div>

        <div className="h-72 w-full">
          {loading ? (
            <div className="h-full flex items-center justify-center text-xs text-slate-400">
              Loading anomaly time series...
            </div>
          ) : !anomalyData?.time_series?.length ? (
            <div className="h-full flex items-center justify-center text-xs text-slate-400">
              No data points available for this selection.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={anomalyData.time_series} margin={{ top: 10, right: 20, left: 20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis
                  dataKey="period"
                  stroke="#94a3b8"
                  fontSize={10}
                  tickLine={false}
                  minTickGap={25}
                />
                <YAxis
                  stroke="#94a3b8"
                  fontSize={10}
                  width={64}
                  tickLine={false}
                  tickFormatter={(val) => {
                    if (metric === 'gross_revenue') return formatCompact(val, 'R$');
                    if (metric === 'on_time_delivery_rate') return `${val}%`;
                    return val.toLocaleString();
                  }}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload || !payload.length) return null;
                    const pt = payload[0].payload;
                    return (
                      <div className="bg-slate-900 text-white p-3 rounded-lg shadow-xl text-xs space-y-1">
                        <p className="font-bold border-b border-slate-700 pb-1">{pt.period}</p>
                        <p className="text-slate-300">
                          Observed: <span className="font-semibold text-white">{formatValue(pt.observed, metric)}</span>
                        </p>
                        {pt.expected !== null && pt.expected !== undefined && (
                          <p className="text-slate-400">
                            Expected: {formatValue(pt.expected, metric)}
                          </p>
                        )}
                        {pt.is_anomaly && (
                          <div className="pt-1 border-t border-slate-700 mt-1">
                            <span className="inline-block px-1.5 py-0.5 rounded text-2xs font-bold uppercase bg-rose-900/60 text-rose-300 border border-rose-700">
                              {pt.severity} anomaly
                            </span>
                            {pt.deviation_score && (
                              <p className="text-2xs text-rose-300 mt-1">
                                Score: {pt.deviation_score.toFixed(2)}
                              </p>
                            )}
                            {pt.known_event && (
                              <p className="text-2xs text-emerald-400 mt-0.5 font-medium">
                                ★ {pt.known_event}
                              </p>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  }}
                />
                <Legend verticalAlign="top" height={36} iconSize={8} wrapperStyle={{ fontSize: '11px' }} />
                <Line
                  type="monotone"
                  dataKey="observed"
                  name="Observed"
                  stroke="#4f46e5"
                  strokeWidth={1.8}
                  dot={renderCustomDot}
                  activeDot={{ r: 6 }}
                />
                <Line
                  type="monotone"
                  dataKey="expected"
                  name="Baseline (Expected)"
                  stroke="#94a3b8"
                  strokeWidth={1.2}
                  strokeDasharray="4 4"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Detailed Anomalies Table */}
      <div className="bg-white rounded-xl border border-slate-200/80 shadow-2xs overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <h2 className="text-sm font-bold text-slate-900">
            Detected Anomalies Log ({displayedAnomalies.length})
          </h2>
          <span className="text-2xs text-slate-400">Filtered by severity: {severity}</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs min-w-[56rem]">
            <thead className="bg-slate-50/80 text-slate-500 font-semibold border-b border-slate-200/60 uppercase tracking-wider text-2xs">
              <tr>
                <th className="py-3 px-4">Period</th>
                <th className="py-3 px-4">Metric</th>
                <th className="py-3 px-4">Direction</th>
                <th className="py-3 px-4 text-right">Observed</th>
                <th className="py-3 px-4 text-right">Expected</th>
                <th className="py-3 px-4 text-right">Dev Score</th>
                <th className="py-3 px-4">Severity</th>
                <th className="py-3 px-4">Method</th>
                <th className="py-3 px-4">Known Event Candidate</th>
                <th className="py-3 px-4">Why?</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {loading ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-slate-400">
                    Loading anomaly table...
                  </td>
                </tr>
              ) : displayedAnomalies.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-slate-400">
                    No anomalies detected matching the current criteria.
                  </td>
                </tr>
              ) : (
                displayedAnomalies.map((item, idx) => {
                  const isSpike = item.direction === 'spike';
                  return (
                    <tr key={idx} className="hover:bg-slate-50/60 transition">
                      <td className="py-3 px-4 font-mono font-medium text-slate-900">{item.period}</td>
                      <td className="py-3 px-4 font-semibold text-slate-800">{item.metric}</td>
                      <td className="py-3 px-4">
                        <span className={`inline-flex items-center space-x-1 px-2 py-0.5 rounded text-2xs font-semibold ${
                          isSpike ? 'bg-indigo-50 text-indigo-700' : 'bg-rose-50 text-rose-700'
                        }`}>
                          {isSpike ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                          <span>{item.direction}</span>
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right font-mono font-bold text-slate-900">
                        {formatValue(item.observed, item.metric)}
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-slate-500">
                        {formatValue(item.expected, item.metric)}
                      </td>
                      <td className="py-3 px-4 text-right font-mono font-semibold text-slate-800">
                        {item.deviation_score.toFixed(2)}
                      </td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-0.5 rounded text-2xs font-bold uppercase ${
                          item.severity === 'high'
                            ? 'bg-rose-100 text-rose-800 border border-rose-200'
                            : (item.severity === 'medium'
                              ? 'bg-amber-100 text-amber-800 border border-amber-200'
                              : 'bg-blue-100 text-blue-800 border border-blue-200')
                        }`}>
                          {item.severity}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-2xs font-mono text-slate-500">{item.method}</td>
                      <td className="py-3 px-4">
                        {item.known_event_candidate ? (
                          <span className="text-emerald-700 font-medium text-2xs bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                            ★ {item.known_event_candidate}
                          </span>
                        ) : (
                          <span className="text-slate-400 text-2xs">—</span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        {item.dimension === 'overall' && (
                          <ExplainButton onClick={() => setExplainTarget({ source: { kind: 'olist' }, metric, period: item.period, grain })} />
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
      <AnomalyExplainDrawer target={explainTarget} onClose={() => setExplainTarget(null)} />
    </div>
  );
};
