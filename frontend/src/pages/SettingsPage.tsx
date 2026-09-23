import React from 'react';
import { Settings, Sparkles, Database, Sliders, Shield } from 'lucide-react';

export const SettingsPage: React.FC = () => {
  return (
    <div className="space-y-8 pb-12">
      {/* Page Heading */}
      <div className="border-b border-slate-200/80 pb-4">
        <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Settings</h1>
        <p className="text-xs text-slate-500 mt-1">
          Manage your InsightForge workspace and application preferences.
        </p>
      </div>

      {/* Workspace Preferences */}
      <section className="bg-white border border-slate-200/80 rounded-xl p-6 shadow-xs space-y-6">
        <div className="flex items-center space-x-3 border-b border-slate-100 pb-3">
          <div className="p-2 bg-indigo-50 border border-indigo-100 rounded-lg text-indigo-600">
            <Sliders className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900 tracking-tight">Workspace Preferences</h2>
            <p className="text-xs text-slate-500">General display and regional formatting defaults</p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 text-xs">
          <div className="space-y-1.5">
            <label className="font-semibold text-slate-700">Display Theme</label>
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-slate-800 font-medium flex items-center justify-between">
              <span>Light Theme (SaaS Modern)</span>
              <span className="text-[10px] bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded font-bold">Active</span>
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="font-semibold text-slate-700">Currency Formatting</label>
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-slate-800 font-medium flex items-center justify-between">
              <span>Indian Rupee (₹)</span>
              <span className="text-slate-500 text-[11px]">INR</span>
            </div>
          </div>
        </div>
      </section>

      {/* AI Model Configuration */}
      <section className="bg-white border border-slate-200/80 rounded-xl p-6 shadow-xs space-y-6">
        <div className="flex items-center space-x-3 border-b border-slate-100 pb-3">
          <div className="p-2 bg-blue-50 border border-blue-100 rounded-lg text-blue-600">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900 tracking-tight">AI Engine Configuration</h2>
            <p className="text-xs text-slate-500">Configured natural-language processing & grounding parameters</p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
          <div className="p-4 bg-slate-50 border border-slate-200/80 rounded-xl space-y-1">
            <span className="text-slate-500 font-medium">Active LLM Model</span>
            <div className="text-sm font-bold text-slate-900">Gemini 2.5 Flash</div>
            <div className="text-[11px] text-slate-500">Google GenAI SDK</div>
          </div>

          <div className="p-4 bg-slate-50 border border-slate-200/80 rounded-xl space-y-1">
            <span className="text-slate-500 font-medium">Data Grounding</span>
            <div className="text-sm font-bold text-emerald-700">Strict PostgreSQL</div>
            <div className="text-[11px] text-slate-500">Zero Arbitrary SQL</div>
          </div>

          <div className="p-4 bg-slate-50 border border-slate-200/80 rounded-xl space-y-1">
            <span className="text-slate-500 font-medium">Intent Allow-List</span>
            <div className="text-sm font-bold text-slate-900">8 Supported Intents</div>
            <div className="text-[11px] text-slate-500">Threshold: 60% Confidence</div>
          </div>
        </div>
      </section>

      {/* Database Connection Info */}
      <section className="bg-white border border-slate-200/80 rounded-xl p-6 shadow-xs space-y-6">
        <div className="flex items-center space-x-3 border-b border-slate-100 pb-3">
          <div className="p-2 bg-emerald-50 border border-emerald-100 rounded-lg text-emerald-600">
            <Database className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900 tracking-tight">Database Connectivity</h2>
            <p className="text-xs text-slate-500">PostgreSQL engine connection status</p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
          <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-between">
            <span className="text-slate-600 font-medium">Engine</span>
            <span className="font-bold text-slate-900">PostgreSQL 16</span>
          </div>

          <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-between">
            <span className="text-slate-600 font-medium">Connection Status</span>
            <span className="font-bold text-emerald-700 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-600"></span>
              Connected
            </span>
          </div>
        </div>
      </section>
    </div>
  );
};
