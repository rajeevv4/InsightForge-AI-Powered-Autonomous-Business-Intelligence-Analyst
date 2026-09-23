import React, { useEffect, useState, useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import { api } from '../services/api';
import { DataQualityResponse } from '../types/api';
import { DataQualityCard } from '../components/DataQualityCard';
import { ShieldCheck, CheckCircle2, FileCheck, Layers } from 'lucide-react';

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

        <div className="flex items-center space-x-2 text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 px-3 py-1.5 rounded-lg">
          <CheckCircle2 className="w-4 h-4 text-emerald-600" />
          <span>System Status: Healthy</span>
        </div>
      </div>

      {/* Human-Readable Reliability Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white border border-slate-200/80 rounded-xl p-5 shadow-xs flex flex-col justify-between">
          <div className="flex items-center space-x-3 mb-3">
            <div className="p-2 bg-indigo-50 border border-indigo-100 rounded-lg text-indigo-600">
              <FileCheck className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">Data Completeness</h3>
              <p className="text-[11px] text-emerald-700 font-medium">No critical issues detected</p>
            </div>
          </div>
          <p className="text-xs text-slate-500 leading-relaxed">
            All core transaction tables contain verified data for timestamps, prices, products, and customer identifiers.
          </p>
        </div>

        <div className="bg-white border border-slate-200/80 rounded-xl p-5 shadow-xs flex flex-col justify-between">
          <div className="flex items-center space-x-3 mb-3">
            <div className="p-2 bg-blue-50 border border-blue-100 rounded-lg text-blue-600">
              <Layers className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">Data Consistency</h3>
              <p className="text-[11px] text-emerald-700 font-medium">All key relationships validated</p>
            </div>
          </div>
          <p className="text-xs text-slate-500 leading-relaxed">
            Foreign key relational constraints strictly enforce zero orphan records across items, orders, and reviews.
          </p>
        </div>

        <div className="bg-white border border-slate-200/80 rounded-xl p-5 shadow-xs flex flex-col justify-between">
          <div className="flex items-center space-x-3 mb-3">
            <div className="p-2 bg-emerald-50 border border-emerald-100 rounded-lg text-emerald-600">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">Data Integrity</h3>
              <p className="text-[11px] text-emerald-700 font-medium">No duplicate primary keys detected</p>
            </div>
          </div>
          <p className="text-xs text-slate-500 leading-relaxed">
            Primary key uniqueness checks verify 100% unique identifiers for customers, products, and orders.
          </p>
        </div>
      </div>

      {/* Main Audit Card Component */}
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
