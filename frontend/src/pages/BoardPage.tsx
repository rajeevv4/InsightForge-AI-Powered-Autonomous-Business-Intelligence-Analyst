import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Bookmark,
  RefreshCw,
  Trash2,
  Sparkles,
  AlertCircle,
  Clock,
  Database,
  Code,
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  Legend,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import { api } from '../services/api';
import { getPinnedCards, removePinnedCard } from '../lib/pinnedBoard';
import { PinnedCardSpec, SQLRerunResponse } from '../types/api';
import { formatMoney } from '../lib/format';
import { useUi } from '../contexts/UiContext';

interface CardRuntimeState {
  loading: boolean;
  data?: SQLRerunResponse;
  error?: string;
  expired?: boolean;
  showSql?: boolean;
}

const PIE_COLORS = ['#4f46e5', '#0ea5e9', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#14b8a6', '#f97316'];

export const BoardPage: React.FC = () => {
  const [pins, setPins] = useState<PinnedCardSpec[]>(() => getPinnedCards());
  const [runtime, setRuntime] = useState<Record<string, CardRuntimeState>>({});
  const { currency: pickedCurrency } = useUi();

  const runPin = async (pin: PinnedCardSpec) => {
    setRuntime((prev) => ({
      ...prev,
      [pin.id]: { ...prev[pin.id], loading: true, error: undefined, expired: false },
    }));

    try {
      let res: SQLRerunResponse;
      if (pin.dataset_id === 'olist_demo') {
        res = await api.rerunOlistPin({
          route: pin.route,
          intent: pin.intent,
          sql: pin.sql,
        });
      } else {
        res = await api.rerunDatasetPin(pin.dataset_id, pin.sql || '');
      }
      setRuntime((prev) => ({
        ...prev,
        [pin.id]: { ...prev[pin.id], loading: false, data: res, error: undefined, expired: false },
      }));
    } catch (err: any) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail || '';
      const isExpired =
        pin.dataset_id !== 'olist_demo' &&
        (status === 404 || status === 410 || /not found|expired|deleted/i.test(detail));
      setRuntime((prev) => ({
        ...prev,
        [pin.id]: {
          ...prev[pin.id],
          loading: false,
          expired: isExpired,
          error: isExpired ? 'Dataset expired' : detail || 'Failed to refresh pinned query.',
        },
      }));
    }
  };

  const refreshAll = (list: PinnedCardSpec[] = pins) => {
    list.forEach((p) => runPin(p));
  };

  useEffect(() => {
    if (pins.length > 0) {
      refreshAll(pins);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleUnpin = (id: string) => {
    const next = removePinnedCard(id);
    setPins(next);
  };

  const formatVal = (col: string, val: any, isOlist: boolean) => {
    if (val === null || val === undefined) return '—';
    if (typeof val === 'number') {
      const lower = col.toLowerCase();
      if (
        lower.includes('price') ||
        lower.includes('revenue') ||
        lower.includes('freight') ||
        lower.includes('amount') ||
        lower.includes('value')
      ) {
        return formatMoney(val, isOlist ? 'R$' : pickedCurrency);
      }
      return Number.isInteger(val) ? val.toLocaleString() : val.toFixed(2);
    }
    return String(val);
  };

  return (
    <div className="space-y-6">
      <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center space-x-3">
          <div className="p-2.5 bg-indigo-50 text-indigo-600 rounded-xl">
            <Bookmark className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-bold text-slate-900">My Board (Live Pinned Queries)</h1>
            <p className="text-xs text-slate-500">
              Stores only query specs & chart types—never raw rows. Every card re-runs live through guarded endpoints.
            </p>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={() => refreshAll()}
            disabled={pins.length === 0}
            className="inline-flex items-center space-x-1.5 px-3.5 py-2 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 text-slate-700 font-semibold rounded-xl text-xs transition cursor-pointer"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh All</span>
          </button>
          <Link
            to="/ask"
            className="inline-flex items-center space-x-1.5 px-3.5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-xl text-xs transition"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Ask & Pin New</span>
          </Link>
        </div>
      </div>

      {pins.length === 0 ? (
        <div className="bg-white border border-dashed border-slate-300 rounded-2xl p-10 text-center space-y-3">
          <Bookmark className="w-8 h-8 text-slate-300 mx-auto" />
          <h2 className="text-sm font-bold text-slate-800">No pinned insights yet</h2>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            Ask any question on the Ask InsightForge page and click <strong>Pin to Board</strong> to save it as a live, auto-refreshing card here.
          </p>
          <Link
            to="/ask"
            className="inline-flex items-center space-x-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-xl text-xs transition"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Go to Ask AI</span>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {pins.map((pin) => {
            const state = runtime[pin.id] || { loading: true };
            const rows = state.data?.rows || [];
            const cols = state.data?.columns || [];
            const isOlist = pin.dataset_id === 'olist_demo';
            const stringCol = cols.find((c) => typeof rows[0]?.[c] === 'string');
            const numericCol = cols.find((c) => typeof rows[0]?.[c] === 'number');
            const canChart = Boolean(
              pin.chart_spec !== 'table' && rows.length > 0 && stringCol && numericCol && rows.length <= 50
            );

            return (
              <div key={pin.id} className="bg-white border border-slate-200/80 rounded-2xl shadow-xs overflow-hidden flex flex-col">
                <div className="px-5 py-3.5 bg-slate-50/70 border-b border-slate-200/60 flex items-start justify-between gap-3">
                  <div className="space-y-1 min-w-0">
                    <div className="flex items-center space-x-2 text-[11px] text-slate-500">
                      <span className="inline-flex items-center space-x-1 font-semibold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-md">
                        <Database className="w-3 h-3" />
                        <span>{pin.dataset_name}</span>
                      </span>
                      <span className="uppercase font-mono text-[10px] bg-slate-200/70 text-slate-700 px-1.5 py-0.5 rounded">
                        {pin.chart_spec}
                      </span>
                      {state.data?.execution_time_ms !== undefined && (
                        <span className="font-mono text-[10px] text-slate-400">
                          {state.data.execution_time_ms.toFixed(0)}ms
                        </span>
                      )}
                    </div>
                    <h3 className="text-sm font-bold text-slate-900 truncate" title={pin.question}>
                      {pin.question}
                    </h3>
                  </div>

                  <div className="flex items-center space-x-1 shrink-0">
                    {pin.sql && (
                      <button
                        type="button"
                        onClick={() =>
                          setRuntime((prev) => ({
                            ...prev,
                            [pin.id]: { ...prev[pin.id], showSql: !prev[pin.id]?.showSql },
                          }))
                        }
                        title="Toggle SQL"
                        className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition cursor-pointer"
                      >
                        <Code className="w-3.5 h-3.5" />
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => runPin(pin)}
                      disabled={state.loading}
                      title="Refresh card"
                      className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition cursor-pointer"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${state.loading ? 'animate-spin text-indigo-600' : ''}`} />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleUnpin(pin.id)}
                      title="Remove from board"
                      className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition cursor-pointer"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {state.showSql && pin.sql && (
                  <div className="p-3 bg-slate-900 text-[11px] font-mono text-emerald-300 overflow-x-auto">
                    <pre className="whitespace-pre-wrap">{pin.sql}</pre>
                  </div>
                )}

                <div className="p-5 flex-1">
                  {state.loading ? (
                    <div className="h-48 flex items-center justify-center text-xs text-slate-400 space-x-2">
                      <RefreshCw className="w-4 h-4 animate-spin text-indigo-500" />
                      <span>Re-running guarded query...</span>
                    </div>
                  ) : state.expired ? (
                    <div className="h-48 flex flex-col items-center justify-center text-center space-y-2 bg-amber-50/60 border border-amber-200 rounded-xl p-4">
                      <Clock className="w-6 h-6 text-amber-600" />
                      <div className="text-xs font-bold text-amber-900">Dataset expired</div>
                      <p className="text-[11px] text-amber-700 max-w-xs">
                        This uploaded dataset is no longer available or its session expired. You can unpin this card.
                      </p>
                    </div>
                  ) : state.error ? (
                    <div className="h-48 flex flex-col items-center justify-center text-center space-y-2 bg-rose-50/60 border border-rose-200 rounded-xl p-4">
                      <AlertCircle className="w-5 h-5 text-rose-600" />
                      <div className="text-xs font-semibold text-rose-800">{state.error}</div>
                    </div>
                  ) : canChart ? (
                    <div className="h-56 w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        {pin.chart_spec === 'line' ? (
                          <LineChart data={rows} margin={{ top: 10, right: 15, left: 10, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                            <XAxis dataKey={stringCol || 'label'} stroke="#94a3b8" fontSize={10} tickLine={false} />
                            <YAxis stroke="#94a3b8" fontSize={10} tickLine={false} />
                            <Tooltip />
                            <Line type="monotone" dataKey={numericCol || 'value'} stroke="#4f46e5" strokeWidth={2.5} dot={{ r: 3 }} />
                          </LineChart>
                        ) : pin.chart_spec === 'pie' ? (
                          <PieChart>
                            <Pie
                              data={rows.slice(0, 8)}
                              dataKey={numericCol || 'value'}
                              nameKey={stringCol || 'label'}
                              cx="50%"
                              cy="50%"
                              outerRadius={72}
                              label
                            >
                              {rows.slice(0, 8).map((_, idx) => (
                                <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                              ))}
                            </Pie>
                            <Tooltip />
                            <Legend wrapperStyle={{ fontSize: '10px' }} />
                          </PieChart>
                        ) : (
                          <BarChart data={rows} margin={{ top: 10, right: 15, left: 10, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                            <XAxis dataKey={stringCol || 'label'} stroke="#94a3b8" fontSize={10} tickLine={false} />
                            <YAxis stroke="#94a3b8" fontSize={10} tickLine={false} />
                            <Tooltip />
                            <Bar dataKey={numericCol || 'value'} fill="#4f46e5" radius={[4, 4, 0, 0]} />
                          </BarChart>
                        )}
                      </ResponsiveContainer>
                    </div>
                  ) : rows.length > 0 ? (
                    <div className="overflow-x-auto max-h-56 border border-slate-100 rounded-xl">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200/60 text-[10px] uppercase">
                          <tr>
                            {cols.map((c) => (
                              <th key={c} className="py-2 px-3 font-mono">{c}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 font-mono text-slate-700">
                          {rows.slice(0, 12).map((r, rIdx) => (
                            <tr key={rIdx}>
                              {cols.map((c) => (
                                <td key={c} className="py-1.5 px-3 whitespace-nowrap">
                                  {formatVal(c, r[c], isOlist)}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="h-32 flex items-center justify-center text-xs text-slate-400">
                      Query returned 0 rows.
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
