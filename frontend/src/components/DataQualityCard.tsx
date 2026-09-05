import React from 'react';
import { ShieldCheck, CheckCircle2, AlertCircle } from 'lucide-react';
import { DataQualityResponse } from '../types/api';
import { LoadingSpinner } from './LoadingSpinner';
import { ErrorBanner } from './ErrorBanner';

interface DataQualityCardProps {
  data: DataQualityResponse | null;
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
}

export const DataQualityCard: React.FC<DataQualityCardProps> = ({
  data,
  loading,
  error,
  onRetry
}) => {
  if (loading) return <LoadingSpinner message="Auditing PostgreSQL database quality..." />;
  if (error || !data) return <ErrorBanner message={error || 'Failed to load data quality monitor'} onRetry={onRetry} />;

  const isPass = data.audit_status === 'PASS';

  return (
    <div className="bg-slate-900/70 border border-slate-800/80 rounded-xl p-5 shadow-lg shadow-black/20">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-white tracking-tight">Data Quality Monitor</h2>
            <p className="text-xs text-slate-400">Automated 10-point PostgreSQL database integrity and fan-out protection audit</p>
          </div>
        </div>

        <div className={`px-3 py-1 rounded-full border text-xs font-bold uppercase tracking-wider ${
          isPass ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
        }`}>
          {isPass ? '● 100% AUDIT PASS' : '⚠️ WARNINGS FLAGGED'}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
        
        <div className="bg-slate-800/40 border border-slate-700/40 rounded-lg p-3">
          <div className="flex items-center space-x-2 text-slate-300 font-semibold mb-1">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>Primary Key Uniqueness</span>
          </div>
          <p className="text-slate-400 font-mono text-[11px]">{data.primary_key_uniqueness}</p>
        </div>

        <div className="bg-slate-800/40 border border-slate-700/40 rounded-lg p-3">
          <div className="flex items-center space-x-2 text-slate-300 font-semibold mb-1">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>Foreign Key Integrity</span>
          </div>
          <p className="text-slate-400 font-mono text-[11px]">{data.foreign_key_integrity}</p>
        </div>

        <div className="bg-slate-800/40 border border-slate-700/40 rounded-lg p-3">
          <div className="flex items-center space-x-2 text-slate-300 font-semibold mb-1">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>Domain Value Bounds</span>
          </div>
          <p className="text-slate-400 font-mono text-[11px]">{data.domain_bounds_status}</p>
        </div>

        <div className="bg-slate-800/40 border border-slate-700/40 rounded-lg p-3">
          <div className="flex items-center space-x-2 text-slate-300 font-semibold mb-1">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>Join Fan-Out Protection</span>
          </div>
          <p className="text-slate-400 font-mono text-[11px]">{data.join_safety_status}</p>
        </div>

      </div>
    </div>
  );
};
