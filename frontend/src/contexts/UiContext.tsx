import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react';
import { useActiveDataset } from './ActiveDatasetContext';
import { CurrencyCode, formatCompact, formatMoney, formatNumber, isMoneyMeasure } from '../lib/format';

/* ------------------------------------------------------------------ theme */
type Theme = 'light' | 'dark';
const THEME_KEY = 'insightforge_theme';
const readTheme = (): Theme => {
  try { return localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light'; } catch { return 'light'; }
};

/* ------------------------------------------------------------------ toasts */
export type ToastKind = 'success' | 'error' | 'info';
interface Toast { id: number; kind: ToastKind; title: string; message?: string }

/* ------------------------------------------------------------------ context */
interface UiContextValue {
  theme: Theme;
  toggleTheme: () => void;
  /** Effective currency for the active dataset: always R$ for the Olist demo; the user's pick for uploads. */
  currency: CurrencyCode;
  setCurrency: (c: CurrencyCode) => void;
  canPickCurrency: boolean;
  /** Format a measure value: money measures get the currency, everything else is a plain number. */
  fmtMeasure: (value: number | null | undefined, measure?: { name?: string | null; column?: string | null; aggregation?: string | null }) => string;
  fmtMeasureCompact: (value: number, measure?: { name?: string | null; column?: string | null; aggregation?: string | null }) => string;
  measureCurrency: (measure?: { name?: string | null; column?: string | null; aggregation?: string | null }) => CurrencyCode;
  toast: (kind: ToastKind, title: string, message?: string) => void;
}

const UiContext = createContext<UiContextValue | null>(null);
const currencyKey = (id: string) => `insightforge_currency_${id}`;

export const UiProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isOlist, activeDatasetId } = useActiveDataset();
  const [theme, setTheme] = useState<Theme>(readTheme);
  const [currencyMap, setCurrencyMap] = useState<Record<string, CurrencyCode>>({});
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    try { localStorage.setItem(THEME_KEY, theme); } catch { /* private mode */ }
  }, [theme]);

  const stored = (id: string): CurrencyCode => {
    if (id in currencyMap) return currencyMap[id];
    try { return (localStorage.getItem(currencyKey(id)) as CurrencyCode) || ''; } catch { return ''; }
  };
  const currency: CurrencyCode = isOlist ? 'R$' : stored(activeDatasetId);

  const setCurrency = useCallback((c: CurrencyCode) => {
    if (isOlist) return;
    setCurrencyMap((m) => ({ ...m, [activeDatasetId]: c }));
    try { localStorage.setItem(currencyKey(activeDatasetId), c); } catch { /* private mode */ }
  }, [isOlist, activeDatasetId]);

  const measureCurrency = useCallback((m?: { name?: string | null; column?: string | null; aggregation?: string | null }): CurrencyCode => {
    if (!currency || !m) return '';
    const agg = (m.aggregation || '').toUpperCase();
    if (agg === 'COUNT') return '';
    return isMoneyMeasure(m.name, m.column) ? currency : '';
  }, [currency]);

  const fmtMeasure = useCallback((v: number | null | undefined, m?: { name?: string | null; column?: string | null; aggregation?: string | null }) => {
    const cur = measureCurrency(m);
    if (cur) return formatMoney(v, cur);
    const avg = (m?.aggregation || '').toUpperCase() === 'AVG';
    return formatNumber(v, { avg });
  }, [measureCurrency]);

  const fmtMeasureCompact = useCallback((v: number, m?: { name?: string | null; column?: string | null; aggregation?: string | null }) =>
    formatCompact(v, measureCurrency(m)), [measureCurrency]);

  const toast = useCallback((kind: ToastKind, title: string, message?: string) => {
    const id = nextId.current++;
    setToasts((t) => [...t.slice(-3), { id, kind, title, message }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === 'error' ? 7000 : 4500);
  }, []);

  const value = useMemo<UiContextValue>(() => ({
    theme, toggleTheme: () => setTheme((t) => (t === 'dark' ? 'light' : 'dark')),
    currency, setCurrency, canPickCurrency: !isOlist,
    fmtMeasure, fmtMeasureCompact, measureCurrency, toast,
  }), [theme, currency, setCurrency, isOlist, fmtMeasure, fmtMeasureCompact, measureCurrency, toast]);

  return (
    <UiContext.Provider value={value}>
      {children}
      <div className="fixed bottom-4 right-4 z-[70] flex flex-col gap-2 w-[min(22rem,calc(100vw-2rem))]" aria-live="polite" role="status">
        {toasts.map((t) => (
          <div key={t.id} className={`animate-toast-in flex items-start gap-2.5 rounded-xl border bg-white shadow-lift px-3.5 py-3 ${
            t.kind === 'success' ? 'border-emerald-200' : t.kind === 'error' ? 'border-rose-200' : 'border-indigo-200'}`}>
            {t.kind === 'success' ? <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              : t.kind === 'error' ? <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
              : <Info className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />}
            <div className="min-w-0 flex-1">
              <div className="text-xs font-semibold text-slate-900">{t.title}</div>
              {t.message && <div className="text-[11px] text-slate-500 mt-0.5 break-words">{t.message}</div>}
            </div>
            <button onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))} aria-label="Dismiss notification"
              className="text-slate-400 hover:text-slate-600 cursor-pointer"><X className="w-3.5 h-3.5" /></button>
          </div>
        ))}
      </div>
    </UiContext.Provider>
  );
};

export const useUi = (): UiContextValue => {
  const ctx = useContext(UiContext);
  if (!ctx) throw new Error('useUi must be used inside UiProvider');
  return ctx;
};
