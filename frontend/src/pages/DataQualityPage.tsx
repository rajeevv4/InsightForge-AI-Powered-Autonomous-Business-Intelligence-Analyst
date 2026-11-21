import React, { useEffect, useState, useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import { api } from '../services/api';
import { DataQualityResponse } from '../types/api';
import { DataQualityCard } from '../components/DataQualityCard';
import { CheckCircle2, AlertTriangle } from 'lucide-react';

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

  const isHealthy = dataQuality?.audit_status === 'PASS';

  return (
    <div className="space-y-8 pb-12">
      {/* Page Heading */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200/80 pb-4">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
            Data Quality
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Monitor the reliability and completeness of the data used by InsightForge.
          </p>
        </div>

        {dataQuality && (
          <div className={`flex items-center space-x-2 text-xs font-medium px-3 py-1.5 rounded-lg border ${
            isHealthy
              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
              : 'bg-rose-50 text-rose-700 border-rose-200'
          }`}>
            {isHealthy
              ? <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              : <AlertTriangle className="w-4 h-4 text-rose-600" />
            }
            <span>System Status: {isHealthy ? 'Healthy' : 'Issues Detected'}</span>
          </div>
        )}
      </div>

      {/* Main Audit Card Component (renders all data from API) */}
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
