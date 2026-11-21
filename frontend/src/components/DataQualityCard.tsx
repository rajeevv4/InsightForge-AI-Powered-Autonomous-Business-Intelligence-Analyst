import React from 'react';
import { DataQualityResponse } from '../types/api';
import { LoadingSpinner } from './LoadingSpinner';
import { ErrorBanner } from './ErrorBanner';
import { CheckCircle2, XCircle, ShieldCheck, Database, FileCheck, Layers, AlertTriangle } from 'lucide-react';

interface DataQualityCardProps {
  data: DataQualityResponse | null;
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
}

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const isPass = status.startsWith('PASS');
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full ${
      isPass ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700 border border-rose-200'
    }`}>
      {isPass ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
      {status}
    </span>
  );
};

export const DataQualityCard: React.FC<DataQualityCardProps> = ({
  data,
  loading,
  error,
  onRetry
}) => {
  if (loading) return <LoadingSpinner message="Evaluating data quality & completeness..." />;
  if (error || !data) return <ErrorBanner message={error || 'Failed to load data quality audit'} onRetry={onRetry} />;

  const isHealthy = data.audit_status === 'PASS';

  return (
    <div className="bg-white border border-slate-200/80 rounded-xl p-6 shadow-xs space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
        <div>
          <h2 className="text-base font-bold text-slate-900 tracking-tight flex items-center gap-2">
            Data Reliability Summary
            <span className={`text-xs px-2.5 py-0.5 rounded-full font-semibold border ${
              isHealthy ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-rose-50 text-rose-700 border-rose-200'
            }`}>
              {isHealthy ? 'Verified' : 'Issues Found'}
            </span>
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Automated completeness and relationship validation for InsightForge analytics
          </p>
        </div>

        <div className={`flex items-center space-x-2 text-xs px-3 py-1.5 rounded-lg border ${
          isHealthy
            ? 'text-slate-600 bg-slate-50 border-slate-200'
            : 'text-rose-600 bg-rose-50 border-rose-200'
        }`}>
          {isHealthy
            ? <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            : <AlertTriangle className="w-4 h-4 text-rose-600" />
          }
          <span className="font-medium">Audit Status: {data.audit_status}</span>
        </div>
      </div>

      {/* Computed Check Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* PK Uniqueness */}
        <div className="p-4 bg-slate-50/80 border border-slate-200/60 rounded-xl space-y-2">
          <div className="flex items-center space-x-2 text-slate-700 font-semibold text-xs">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            <span>Primary Key Uniqueness</span>
          </div>
          <StatusBadge status={data.primary_key_uniqueness} />
        </div>

        {/* FK Integrity */}
        <div className="p-4 bg-slate-50/80 border border-slate-200/60 rounded-xl space-y-2">
          <div className="flex items-center space-x-2 text-slate-700 font-semibold text-xs">
            <Layers className="w-4 h-4 text-blue-600" />
            <span>Foreign Key Integrity</span>
          </div>
          <StatusBadge status={data.foreign_key_integrity} />
        </div>

        {/* Domain Bounds */}
        <div className="p-4 bg-slate-50/80 border border-slate-200/60 rounded-xl space-y-2">
          <div className="flex items-center space-x-2 text-slate-700 font-semibold text-xs">
            <FileCheck className="w-4 h-4 text-indigo-600" />
            <span>Domain &amp; Value Range</span>
          </div>
          <StatusBadge status={data.domain_bounds_status} />
        </div>
      </div>

      {/* Join Safety */}
      <div className="p-4 bg-slate-50/80 border border-slate-200/60 rounded-xl space-y-2">
        <div className="flex items-center space-x-2 text-slate-700 font-semibold text-xs">
          <Database className="w-4 h-4 text-purple-600" />
          <span>Join Fan-Out Safety</span>
        </div>
        <StatusBadge status={data.join_safety_status} />
      </div>

      {/* Anomalies */}
      {data.anomalies_flagged && data.anomalies_flagged.length > 0 && (
        <div className="p-4 bg-amber-50/80 border border-amber-200/60 rounded-xl space-y-2">
          <div className="flex items-center space-x-2 text-amber-700 font-semibold text-xs">
            <AlertTriangle className="w-4 h-4 text-amber-600" />
            <span>Anomalies Flagged ({data.anomalies_flagged.length})</span>
          </div>
          <ul className="text-xs text-slate-700 space-y-1 ml-6 list-disc">
            {data.anomalies_flagged.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Table Row Counts */}
      <div className="pt-2">
        <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-3">
          Verified Database Records
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          {Object.entries(data.table_row_counts || {}).map(([table, count]) => (
            <div key={table} className="p-3 bg-white border border-slate-200/80 rounded-lg flex items-center justify-between">
              <span className="text-slate-600 font-medium capitalize">{table.replace('_', ' ')}</span>
              <span className="font-bold text-slate-900">{count.toLocaleString()}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Missing Values */}
      {data.missing_value_summary && Object.keys(data.missing_value_summary).length > 0 && (
        <div className="pt-2">
          <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-3">
            Missing Value Summary
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            {Object.entries(data.missing_value_summary).map(([field, count]) => (
              <div key={field} className="p-3 bg-white border border-slate-200/80 rounded-lg flex items-center justify-between">
                <span className="text-slate-600 font-medium">{field}</span>
                <span className={`font-bold ${count > 0 ? 'text-amber-600' : 'text-emerald-600'}`}>{count.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
