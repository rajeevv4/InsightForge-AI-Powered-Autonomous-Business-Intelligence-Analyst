import React from 'react';
import { AskInsightForge } from '../components/AskInsightForge';
import { Sparkles } from 'lucide-react';

export const AskPage: React.FC = () => {
  return (
    <div className="space-y-6 pb-12">
      {/* Page Heading */}
      <div className="border-b border-slate-200/80 pb-4">
        <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
          Ask InsightForge
          <span className="text-xs bg-indigo-50 text-indigo-700 border border-indigo-100 px-2.5 py-0.5 rounded-full font-medium">
            AI Assistant
          </span>
        </h1>
        <p className="text-xs text-slate-500 mt-1">
          Ask questions about your business data in plain English. Powered by AI grounded in validated PostgreSQL analytics.
        </p>
      </div>

      {/* Interactive AI Assistant Component */}
      <section>
        <AskInsightForge />
      </section>

      {/* Helpful Product Guide */}
      <section className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
        <div className="flex items-center space-x-2 mb-3 text-slate-900 font-bold text-sm">
          <Sparkles className="w-4 h-4 text-indigo-600" />
          <h3>How to get the best answers from InsightForge</h3>
        </div>
        <p className="text-xs text-slate-600 leading-relaxed max-w-3xl">
          InsightForge analyzes your e-commerce transaction data including gross revenue, monthly sales trends, merchandise categories, geographic customer states, top merchants, delivery SLAs, and payment methods. Ask direct questions to receive verified executive summaries.
        </p>
      </section>
    </div>
  );
};
