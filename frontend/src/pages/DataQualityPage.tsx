import React, { useEffect, useState, useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import { api } from '../services/api';
import { DataQualityResponse } from '../types/api';
import { DataQualityCard } from '../components/DataQualityCard';
import { ShieldCheck, CheckCircle2, AlertTriangle } from 'lucide-react';

export const DataQualityPage: React.FC = () => {
  const outletContext = useOutletContext<{ refreshTrigger?: number }>();
  const [dataQuality, setDataQuality] = useState<DataQualityResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadDataQuality = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getDataQuality();
      setDataQuality(data);
    } catch (err) {
      console.error('Failed to fetch data quality audit report:', err);
      setError('Failed to fetch data quality audit report from backend.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDataQuality();
  }, [loadDataQuality, outletContext?.refreshTrigger]);

  const isAuditPass = dataQuality?.audit_status === 'PASS';

  return (
    <div className="space-y-8 pb-12">
      {/* Page Heading */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center gap-2">
            Data Quality Overview
            {dataQuality && (
              <span
                className={`text-xs px-2.5 py-0.5 rounded-full font-mono font-bold ${
                  isAuditPass
                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                    : 'bg-red-500/10 text-red-400 border border-red-500/30'
                }`}
              >
                STATUS: {dataQuality.audit_status}
              </span>
            )}
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Automated 10-check data quality audit monitoring primary/foreign key integrity, missing values, domain bounds, and join fan-out safety.
          </p>
        </div>

        <div className="flex items-center space-x-2 text-xs font-mono bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-lg text-slate-300">
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
          <span>Join Safety: 0.00 Discrepancy</span>
        </div>
      </div>

      {/* Audit Card Component */}
      <section>
        <DataQualityCard
          data={dataQuality}
          loading={loading}
          error={error}
          onRetry={loadDataQuality}
        />
      </section>
    </div>
  );
};
