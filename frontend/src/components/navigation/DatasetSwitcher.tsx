import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, ChevronDown, Clock, Database, Settings2, X } from 'lucide-react';
import { OLIST_DEMO_ID, isExpired, useActiveDataset } from '../../contexts/ActiveDatasetContext';
import { DatasetSummary } from '../../types/api';

/** "expires in 5h 12m" style countdown for uploaded datasets. */
export const formatExpiry = (expiresAt: string | null | undefined, now: number): string | null => {
  if (!expiresAt) return null;
  const ms = new Date(expiresAt).getTime() - now;
  if (Number.isNaN(ms)) return null;
  if (ms <= 0) return 'expired';
  const mins = Math.floor(ms / 60000);
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return h > 0 ? `expires in ${h}h ${m}m` : `expires in ${m}m`;
};

export const DatasetSwitcher: React.FC = () => {
  const { activeDatasetId, activeDataset, isOlist, datasets, datasetsLoaded, setActiveDatasetId, refreshDatasets, notice, dismissNotice } = useActiveDataset();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const rootRef = useRef<HTMLDivElement>(null);

  // Countdown tick
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 30000);
    return () => window.clearInterval(t);
  }, []);

  // Close on outside click / Escape
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const toggle = () => {
    if (!open) refreshDatasets();
    setOpen((o) => !o);
  };

  const choose = (id: string) => {
    setActiveDatasetId(id);
    setOpen(false);
  };

  const uploads = datasets.filter((d) => !d.is_demo && d.id !== OLIST_DEMO_ID);
  const label = isOlist ? 'Olist demo' : activeDataset?.name || (datasetsLoaded ? 'Uploaded dataset' : 'Loading dataset…');
  const activeExpiry = !isOlist ? formatExpiry(activeDataset?.expires_at, now) : null;

  const row = (d: DatasetSummary | null) => {
    const id = d ? d.id : OLIST_DEMO_ID;
    const selected = id === activeDatasetId;
    const expired = d ? isExpired(d, now) : false;
    const expiry = d ? formatExpiry(d.expires_at, now) : null;
    return (
      <button
        key={id}
        role="option"
        aria-selected={selected}
        disabled={expired}
        onClick={() => choose(id)}
        className={`w-full text-left px-3 py-2 rounded-lg flex items-start gap-2 transition ${
          selected ? 'bg-indigo-50' : 'hover:bg-slate-50'
        } ${expired ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
      >
        <Check className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${selected ? 'text-indigo-600' : 'text-transparent'}`} />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5">
            <span className="text-xs font-semibold text-slate-900 truncate">{d ? d.name : 'Olist E-Commerce'}</span>
            {!d && <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-emerald-100 text-emerald-800 rounded">Demo</span>}
          </span>
          <span className="flex items-center gap-2 text-[10px] text-slate-500 mt-0.5">
            <span className="font-mono">{d ? d.schema_name : 'insightforge'}</span>
            {d && <span>{d.table_count} table{d.table_count === 1 ? '' : 's'} · {d.total_rows.toLocaleString()} rows</span>}
          </span>
          {expiry && (
            <span className={`flex items-center gap-1 text-[10px] mt-0.5 ${expired ? 'text-rose-600' : 'text-amber-700'}`}>
              <Clock className="w-3 h-3" />
              {expiry}
            </span>
          )}
        </span>
      </button>
    );
  };

  return (
    <div ref={rootRef} className="relative inline-flex items-center gap-1.5 min-w-0 max-w-full">
      <button
        onClick={toggle}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Active dataset: ${label}. Change dataset`}
        title={label}
        className={`inline-flex items-center gap-1.5 max-w-[min(18rem,60vw)] px-2.5 py-1 rounded-lg text-[11px] font-semibold border transition cursor-pointer ${
          isOlist
            ? 'bg-slate-100 text-slate-700 border-slate-200 hover:bg-slate-200'
            : 'bg-indigo-50 text-indigo-700 border-indigo-200 hover:bg-indigo-100'
        }`}
      >
        <Database className="w-3.5 h-3.5 shrink-0" />
        <span className="truncate min-w-0">{label}</span>
        <ChevronDown className={`w-3 h-3 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {activeExpiry && (
        <span className="inline-flex items-center gap-1 shrink-0 px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-800 border border-amber-200" title={`This upload ${activeExpiry}`}>
          <Clock className="w-3 h-3" />{activeExpiry.replace('expires in ', '')}
        </span>
      )}

      {notice && (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-amber-50 text-amber-800 border border-amber-200">
          {notice}
          <button onClick={dismissNotice} aria-label="Dismiss notice" className="cursor-pointer">
            <X className="w-3 h-3" />
          </button>
        </span>
      )}

      {open && (
        <div
          role="listbox"
          className="absolute left-0 top-full mt-2 w-[min(20rem,calc(100vw-2rem))] max-h-[70vh] overflow-y-auto bg-white border border-slate-200 rounded-xl shadow-lift p-1.5 z-50 animate-scale-in origin-top-left"
        >
          <div className="px-3 pt-1.5 pb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">Built-in demo</div>
          {row(null)}
          <div className="px-3 pt-2.5 pb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">Your uploads</div>
          {uploads.length === 0 ? (
            <div className="px-3 py-2 text-xs text-slate-500">No uploaded datasets yet.</div>
          ) : (
            uploads.map((d) => row(d))
          )}
          <button
            onClick={() => {
              setOpen(false);
              navigate('/datasets');
            }}
            className="mt-1 w-full text-left px-3 py-2 rounded-lg text-xs text-indigo-600 hover:bg-indigo-50 flex items-center gap-2 cursor-pointer border-t border-slate-100"
          >
            <Settings2 className="w-3.5 h-3.5" />
            Upload or manage datasets
          </button>
        </div>
      )}
    </div>
  );
};
