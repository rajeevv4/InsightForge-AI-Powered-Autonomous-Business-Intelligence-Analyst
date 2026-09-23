import React from 'react';
import { HelpCircle, Sparkles, Database, BarChart3, Mail } from 'lucide-react';

export const HelpPage: React.FC = () => {
  return (
    <div className="space-y-8 pb-12">
      {/* Page Heading */}
      <div className="border-b border-slate-200/80 pb-4">
        <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Help & Information</h1>
        <p className="text-xs text-slate-500 mt-1">
          Learn how InsightForge analyzes your business data and powers natural-language business insights.
        </p>
      </div>

      {/* Overview Card */}
      <section className="bg-white border border-slate-200/80 rounded-xl p-6 shadow-xs space-y-4">
        <div className="flex items-center space-x-3 text-slate-900 font-bold text-base">
          <div className="p-2 bg-indigo-50 border border-indigo-100 rounded-lg text-indigo-600">
            <HelpCircle className="w-5 h-5" />
          </div>
          <h2>What is InsightForge?</h2>
        </div>
        <p className="text-xs text-slate-600 leading-relaxed max-w-4xl">
          InsightForge is an autonomous Business Intelligence platform designed by Rajeev Karakoti. It translates natural-language business queries into validated executive insights, key metrics, charts, and grounded explanations using real transaction data inside PostgreSQL.
        </p>
      </section>

      {/* Dataset & Capabilities */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <section className="bg-white border border-slate-200/80 rounded-xl p-6 shadow-xs space-y-3">
          <div className="flex items-center space-x-2 text-slate-900 font-bold text-sm">
            <Database className="w-4 h-4 text-blue-600" />
            <h3>Analyzed E-Commerce Dataset</h3>
          </div>
          <p className="text-xs text-slate-600 leading-relaxed">
            InsightForge evaluates the official Olist Brazilian E-Commerce public dataset containing ~100,000 orders across 9 core transaction tables. Metrics include Gross Revenue, Product Sales, Shipping Fees, Customer States, Top Merchants, Delivery SLAs, and Payment Methods.
          </p>
        </section>

        <section className="bg-white border border-slate-200/80 rounded-xl p-6 shadow-xs space-y-3">
          <div className="flex items-center space-x-2 text-slate-900 font-bold text-sm">
            <Sparkles className="w-4 h-4 text-indigo-600" />
            <h3>How Ask InsightForge Works</h3>
          </div>
          <p className="text-xs text-slate-600 leading-relaxed">
            When you ask a business question, InsightForge uses Google Gemini 2.5 Flash to understand your business intent, routes the intent to a validated PostgreSQL analytics function, and synthesizes a grounded answer based strictly on the retrieved data.
          </p>
        </section>
      </div>

      {/* Support & Credits */}
      <section className="bg-white border border-slate-200/80 rounded-xl p-6 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-bold text-slate-900">Developed by Rajeev Karakoti</h3>
          <p className="text-xs text-slate-500 mt-0.5">B.Tech Major Project — Autonomous BI & AI Analytics System</p>
        </div>

        <div className="flex items-center space-x-2 text-xs font-semibold text-indigo-600">
          <Mail className="w-4 h-4" />
          <span>InsightForge Support</span>
        </div>
      </section>
    </div>
  );
};
