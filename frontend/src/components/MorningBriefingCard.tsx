import React, { useEffect, useState } from 'react';
import { BellRing, CheckCircle2, AlertTriangle, Settings2, RefreshCw } from 'lucide-react';
import { api } from '../services/api';
import { BriefingThresholds, MorningBriefingResponse } from '../types/api';

const STORAGE_KEY = 'insightforge_briefing_thresholds_v1';

const DEFAULT_THRESHOLDS: BriefingThresholds = {
  max_late_delivery_pct: 7.0,
  min_csat: 4.2,
  min_mom_revenue_pct: -15.0,
  max_high_anomalies: 0,
};

function loadSavedThresholds(): BriefingThresholds {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_THRESHOLDS;
    const p = JSON.parse(raw);
    return {
      max_late_delivery_pct: Number.isFinite(Number(p.max_late_delivery_pct)) ? Number(p.max_late_delivery_pct) : 7.0,
      min_csat: Number.isFinite(Number(p.min_csat)) ? Number(p.min_csat) : 4.2,
      min_mom_revenue_pct: Number.isFinite(Number(p.min_mom_revenue_pct)) ? Number(p.min_mom_revenue_pct) : -15.0,
      max_high_anomalies: Number.isFinite(Number(p.max_high_anomalies)) ? Number(p.max_high_anomalies) : 0,
    };
  } catch {
    return DEFAULT_THRESHOLDS;
  }
}

export const MorningBriefingCard: React.FC = () => {
  const [thresholds, setThresholds] = useState<BriefingThresholds>(() => loadSavedThresholds());
  const [draft, setDraft] = useState<BriefingThresholds>(() => loadSavedThresholds());
  const [showConfig, setShowConfig] = useState<boolean>(false);
  const [data, setData] = useState<MorningBriefingResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchBriefing = async (cfg: BriefingThresholds) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getMorningBriefing(cfg);
      setData(res);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Morning briefing temporarily unavailable.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBriefing(thresholds);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleApply = (e: React.FormEvent) => {
    e.preventDefault();
    localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
    setThresholds(draft);
    setShowConfig(false);
    fetchBriefing(draft);
  };

  return (
    <section className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-2.5">
          <div className="p-2 bg-indigo-50 text-indigo-600 rounded-xl">
            <BellRing className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-sm font-bold text-slate-900">Executive Morning Briefing</h2>
              {data && (
                <span
                  className={`px-2 py-0.5 rounded-full text-[11px] font-bold border ${
                    data.triggered_count > 0
                      ? 'bg-amber-50 text-amber-800 border-amber-200'
                      : 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  }`}
                >
                  {data.triggered_count > 0
                    ? `${data.triggered_count} Alert${data.triggered_count > 1 ? 's' : ''} Triggered`
                    : 'All Thresholds Healthy'}
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-500">
              Deterministic template summary & threshold rules · cached 5 min, zero LLM
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={() => setShowConfig(!showConfig)}
            className="inline-flex items-center space-x-1 px-2.5 py-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 rounded-lg transition cursor-pointer"
          >
            <Settings2 className="w-3.5 h-3.5" />
            <span>Thresholds</span>
          </button>
          <button
            type="button"
            onClick={() => fetchBriefing(thresholds)}
            disabled={loading}
            className="p-1.5 text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition cursor-pointer"
            title="Refresh briefing"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-indigo-600' : ''}`} />
          </button>
        </div>
      </div>

      {showConfig && (
        <form onSubmit={handleApply} className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
            <label className="space-y-1 block">
              <span className="font-semibold text-slate-700">Max Late Delivery (%)</span>
              <input
                type="number"
                step="0.1"
                min="0"
                max="100"
                value={draft.max_late_delivery_pct}
                onChange={(e) => setDraft({ ...draft, max_late_delivery_pct: Number(e.target.value) })}
                className="w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg font-mono"
              />
            </label>
            <label className="space-y-1 block">
              <span className="font-semibold text-slate-700">Min CSAT Score (★)</span>
              <input
                type="number"
                step="0.05"
                min="1"
                max="5"
                value={draft.min_csat}
                onChange={(e) => setDraft({ ...draft, min_csat: Number(e.target.value) })}
                className="w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg font-mono"
              />
            </label>
            <label className="space-y-1 block">
              <span className="font-semibold text-slate-700">Min MoM Revenue (%)</span>
              <input
                type="number"
                step="1"
                min="-100"
                max="100"
                value={draft.min_mom_revenue_pct}
                onChange={(e) => setDraft({ ...draft, min_mom_revenue_pct: Number(e.target.value) })}
                className="w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg font-mono"
              />
            </label>
            <label className="space-y-1 block">
              <span className="font-semibold text-slate-700">Max High Anomalies</span>
              <input
                type="number"
                step="1"
                min="0"
                max="100"
                value={draft.max_high_anomalies}
                onChange={(e) => setDraft({ ...draft, max_high_anomalies: Math.max(0, Math.round(Number(e.target.value))) })}
                className="w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg font-mono"
              />
            </label>
          </div>
          <div className="flex items-center justify-end space-x-2">
            <button
              type="button"
              onClick={() => {
                setDraft(DEFAULT_THRESHOLDS);
                localStorage.setItem(STORAGE_KEY, JSON.stringify(DEFAULT_THRESHOLDS));
                setThresholds(DEFAULT_THRESHOLDS);
                setShowConfig(false);
                fetchBriefing(DEFAULT_THRESHOLDS);
              }}
              className="px-3 py-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 cursor-pointer"
            >
              Reset Defaults
            </button>
            <button
              type="submit"
              className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg transition cursor-pointer"
            >
              Apply & Evaluate
            </button>
          </div>
        </form>
      )}

      {error ? (
        <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-xl p-3">{error}</div>
      ) : loading && !data ? (
        <div className="h-20 flex items-center text-xs text-slate-400 space-x-2">
          <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-500" />
          <span>Evaluating morning briefing & threshold rules...</span>
        </div>
      ) : data ? (
        <div className="space-y-3">
          <p className="text-xs font-semibold text-slate-800">{data.headline}</p>
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-1.5 text-xs text-slate-600">
            {data.bullets.map((b, i) => (
              <li key={i} className="flex items-start space-x-1.5">
                <span className="text-indigo-500 font-bold mt-0.5">•</span>
                <span>{b}</span>
              </li>
            ))}
          </ul>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 pt-1">
            {data.alerts.map((a) => (
              <div
                key={a.id}
                className={`p-2.5 rounded-xl border text-xs flex items-start space-x-2 ${
                  a.triggered
                    ? a.severity === 'critical'
                      ? 'bg-rose-50/70 border-rose-200 text-rose-900'
                      : 'bg-amber-50/70 border-amber-200 text-amber-900'
                    : 'bg-emerald-50/50 border-emerald-200/80 text-emerald-900'
                }`}
              >
                {a.triggered ? (
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5 text-amber-600" />
                ) : (
                  <CheckCircle2 className="w-3.5 h-3.5 shrink-0 mt-0.5 text-emerald-600" />
                )}
                <div className="min-w-0">
                  <div className="font-bold text-[11px] truncate">{a.label}</div>
                  <div className="text-[11px] opacity-90 leading-snug mt-0.5">{a.message}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
};
