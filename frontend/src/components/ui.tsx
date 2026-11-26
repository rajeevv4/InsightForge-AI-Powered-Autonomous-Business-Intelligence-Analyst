import React, { useEffect, useRef, useState } from 'react';
import { ArrowRight, BarChart3, Database, FileText, HelpCircle, LineChart, Search, Sparkles, X } from 'lucide-react';
import { truncateLabel } from '../lib/format';

/* ------------------------------------------------------------------ glossary "?" tooltips */
export const GLOSSARY: Record<string, string> = {
  MAD: 'Median Absolute Deviation: a robust measure of spread. A day is unusual when it is several MADs away from the recent median, so one huge day cannot hide other outliers.',
  MAPE: 'Mean Absolute Percentage Error: the average % the forecast missed by when we hid the last months and predicted them. Lower is better.',
  'N:1': 'Many-to-one join: many rows (e.g. orders) point to exactly one row (e.g. a customer), so joining never duplicates rows or double-counts totals.',
  STL: 'Seasonal-Trend decomposition: splits a series into trend, weekly pattern and leftover noise; big leftovers are anomalies.',
  IQR: 'Interquartile range: groups far outside the middle 50% of all groups are flagged as slice outliers.',
  'Naive baseline': 'The simplest possible forecast (repeat the last value). A useful model should beat it.',
  'Mix shift': 'How far this period\'s split across groups moved away from the usual split. 0% = every group moved in proportion.',
  'Volume vs value': 'Revenue = number of orders x average order value. This splits a change into "more/fewer orders" and "bigger/smaller orders".',
  'Join safety': 'Checks that joining tables does not change totals (no row multiplication).',
};

export const InfoTip: React.FC<{ term: keyof typeof GLOSSARY | string; text?: string; className?: string }> = ({ term, text, className = '' }) => {
  const [open, setOpen] = useState(false);
  const body = text || GLOSSARY[term] || term;
  return (
    <span className={`relative inline-flex align-middle ${className}`}>
      <button
        type="button"
        aria-label={`What is ${term}?`}
        onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        className="inline-flex items-center justify-center w-4 h-4 rounded-full text-slate-400 hover:text-indigo-600 cursor-help"
      >
        <HelpCircle className="w-3.5 h-3.5" />
      </button>
      {open && (
        <span role="tooltip"
          className="animate-scale-in absolute z-50 left-1/2 -translate-x-1/2 top-full mt-1.5 w-60 rounded-lg bg-slate-900 text-white text-[11px] leading-snug font-normal normal-case tracking-normal p-2.5 shadow-lift">
          <span className="font-semibold">{term}: </span>{body}
        </span>
      )}
    </span>
  );
};

/* ------------------------------------------------------------------ KPI count-up */
const reducedMotion = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/** Animates 0 -> value once, then renders format(value) exactly (final text is identical to the static one). */
export const CountUp: React.FC<{ value: number | null | undefined; format: (v: number) => string; duration?: number; className?: string }> = ({ value, format, duration = 900, className }) => {
  const [shown, setShown] = useState<number | null>(value ?? null);
  const raf = useRef<number>();
  useEffect(() => {
    if (value === null || value === undefined || Number.isNaN(value) || reducedMotion()) { setShown(value ?? null); return; }
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(t >= 1 ? value : value * eased);
      if (t < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => { if (raf.current) cancelAnimationFrame(raf.current); };
  }, [value, duration]);
  if (value === null || value === undefined || Number.isNaN(value)) return <span className={className}>—</span>;
  const final = format(value);
  // While counting, keep the layout stable by rendering the final text invisibly underneath.
  return (
    <span className={`relative inline-block tabular-nums ${className || ''}`} aria-label={final}>
      <span className="invisible">{final}</span>
      <span className="absolute inset-0" aria-hidden="true">{shown === value ? final : format(Math.round((shown ?? 0) * 100) / 100)}</span>
    </span>
  );
};

/* ------------------------------------------------------------------ confetti */
const CONFETTI_COLORS = ['#6366f1', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#3b82f6', '#ec4899'];
export const Confetti: React.FC<{ show: boolean; onDone?: () => void }> = ({ show, onDone }) => {
  useEffect(() => {
    if (!show) return;
    const t = window.setTimeout(() => onDone?.(), 3200);
    return () => window.clearTimeout(t);
  }, [show, onDone]);
  if (!show || reducedMotion()) return null;
  return (
    <div className="pointer-events-none fixed inset-0 z-[80] overflow-hidden" aria-hidden="true">
      {Array.from({ length: 70 }).map((_, i) => {
        const left = (i * 37) % 100;
        const delay = (i % 10) * 0.08;
        const dur = 2 + ((i * 13) % 10) / 10;
        const drift = ((i * 53) % 160) - 80;
        return (
          <span key={i} style={{
            left: `${left}%`, top: 0, width: i % 3 ? 8 : 6, height: i % 3 ? 12 : 6,
            background: CONFETTI_COLORS[i % CONFETTI_COLORS.length], borderRadius: i % 4 === 0 ? 9999 : 2,
            animation: `confetti-fall ${dur}s cubic-bezier(0.2, 0.6, 0.4, 1) ${delay}s both`,
            ['--drift' as any]: `${drift}px`, position: 'absolute',
          }} />
        );
      })}
    </div>
  );
};

/* ------------------------------------------------------------------ empty state */
export const EmptyState: React.FC<{
  icon?: React.ReactNode; title: string; message?: string; action?: { label: string; onClick: () => void }; compact?: boolean;
}> = ({ icon, title, message, action, compact }) => (
  <div className={`flex flex-col items-center text-center ${compact ? 'py-6' : 'py-10'} px-4 animate-fade-in`}>
    <div className="relative mb-3">
      <div className="absolute inset-0 rounded-2xl bg-brand-gradient opacity-20 blur-xl" />
      <div className="relative w-14 h-14 rounded-2xl bg-brand-soft border border-indigo-100 flex items-center justify-center text-indigo-600">
        {icon || <Sparkles className="w-6 h-6" />}
      </div>
    </div>
    <div className="text-sm font-semibold text-slate-800">{title}</div>
    {message && <p className="text-xs text-slate-500 mt-1 max-w-md">{message}</p>}
    {action && (
      <button onClick={action.onClick}
        className="mt-3 inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-brand-gradient text-white text-xs font-semibold shadow-soft hover:shadow-glow transition cursor-pointer">
        {action.label}<ArrowRight className="w-3.5 h-3.5" />
      </button>
    )}
  </div>
);

/* ------------------------------------------------------------------ chart tick that truncates with a tooltip */
export const TruncatedTick: React.FC<any> = ({ x, y, payload, max = 16, anchor = 'end', angle = 0, dy = 4 }) => {
  const full = String(payload?.value ?? '');
  return (
    <g transform={`translate(${x},${y})`}>
      <text className="if-tick" x={0} y={0} dy={dy} textAnchor={anchor} fontSize={11} fill="#475569" transform={angle ? `rotate(${angle})` : undefined}>
        <title>{full}</title>
        {truncateLabel(full, max)}
      </text>
    </g>
  );
};

/* ------------------------------------------------------------------ first-visit tour */
const TOUR_KEY = 'insightforge_tour_done';
const STEPS = [
  { icon: <Database className="w-6 h-6" />, title: 'Pick a dataset', text: 'Use the switcher in the header: the Olist demo, or a CSV/XLSX you upload on the Datasets page. Every page follows it.' },
  { icon: <Search className="w-6 h-6" />, title: 'Ask in plain words', text: 'Ask InsightForge turns questions into safe, read-only SQL. Try an example question to start.' },
  { icon: <BarChart3 className="w-6 h-6" />, title: 'Find what changed and why', text: 'Anomalies flags unusual days; the Explain button shows which groups drove each spike or drop.' },
  { icon: <LineChart className="w-6 h-6" />, title: 'Look ahead', text: 'Forecast gives a cautious baseline with confidence bands, and refuses when the data are too noisy.' },
  { icon: <FileText className="w-6 h-6" />, title: 'Share it', text: 'Report builds a one-click summary of everything, on screen and as a PDF.' },
];

export const FirstVisitTour: React.FC = () => {
  const [step, setStep] = useState<number | null>(null);
  useEffect(() => {
    try { if (!localStorage.getItem(TOUR_KEY)) setStep(0); } catch { /* private mode: skip the tour */ }
  }, []);
  if (step === null) return null;
  const done = () => { try { localStorage.setItem(TOUR_KEY, '1'); } catch { /* ignore */ } setStep(null); };
  const s = STEPS[step];
  return (
    <div className="fixed inset-0 z-[75] flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm animate-fade-in" role="dialog" aria-modal="true" aria-label="Welcome tour">
      <div className="relative w-full max-w-md rounded-2xl bg-white shadow-lift border border-slate-200 p-6 animate-scale-in">
        <button onClick={done} aria-label="Skip tour" className="absolute top-3 right-3 p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 cursor-pointer"><X className="w-4 h-4" /></button>
        <div className="text-[10px] font-bold uppercase tracking-wider text-indigo-600">Welcome to InsightForge · {step + 1} / {STEPS.length}</div>
        <div key={step} className="animate-fade-in-up">
          <div className="mt-3 w-12 h-12 rounded-xl bg-brand-gradient text-white flex items-center justify-center shadow-glow">{s.icon}</div>
          <h3 className="mt-3 text-lg font-bold text-slate-900">{s.title}</h3>
          <p className="mt-1 text-sm text-slate-600 leading-relaxed">{s.text}</p>
        </div>
        <div className="mt-5 flex items-center justify-between">
          <div className="flex gap-1.5">{STEPS.map((_, i) => <span key={i} className={`h-1.5 rounded-full transition-all ${i === step ? 'w-6 bg-indigo-600' : 'w-1.5 bg-slate-200'}`} />)}</div>
          <div className="flex gap-2">
            <button onClick={done} className="px-3 py-1.5 text-xs text-slate-500 hover:text-slate-800 cursor-pointer">Skip</button>
            <button onClick={() => (step + 1 < STEPS.length ? setStep(step + 1) : done())}
              className="px-3.5 py-1.5 rounded-lg bg-brand-gradient text-white text-xs font-semibold shadow-soft cursor-pointer">
              {step + 1 < STEPS.length ? 'Next' : 'Get started'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
