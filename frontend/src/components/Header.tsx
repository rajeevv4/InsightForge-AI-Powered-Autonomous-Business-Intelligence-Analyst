import React from 'react';
import { RefreshCw, Database, Activity } from 'lucide-react';
import { HealthResponse } from '../types/api';

interface HeaderProps {
  health: HealthResponse | null;
  loading: boolean;
  onRefresh: () => void;
}

export const Header: React.FC<HeaderProps> = ({ health, loading, onRefresh }) => {
  const isConnected = health?.status === 'healthy' && health?.database === 'connected';

  return (
    <header className="border-b border-slate-800/80 bg-slate-900/60 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        
        {/* Title & Subtitle */}
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-sky-500 to-indigo-600 flex items-center justify-center text-white shadow-lg shadow-sky-500/20">
            <Activity className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-2xl font-bold tracking-tight text-white font-mono">INSIGHTFORGE</h1>
              <span className="px-2 py-0.5 text-[10px] uppercase font-bold tracking-wider bg-sky-500/10 border border-sky-500/30 text-sky-400 rounded-full">
                v0.1.0 BI
              </span>
            </div>
            <p className="text-xs text-slate-400 font-medium">
              AI-Powered Autonomous Business Intelligence Analyst
            </p>
          </div>
        </div>

        {/* Status Indicator & Refresh Controls */}
        <div className="flex items-center space-x-4 self-end sm:self-center">
          <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-slate-800/60 border border-slate-700/60 text-xs">
            <Database className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-slate-300 font-medium">PostgreSQL:</span>
            {isConnected ? (
              <span className="flex items-center space-x-1.5 text-emerald-400 font-medium">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span>Connected</span>
              </span>
            ) : (
              <span className="flex items-center space-x-1.5 text-rose-400 font-medium">
                <span className="w-2 h-2 rounded-full bg-rose-400"></span>
                <span>Disconnected</span>
              </span>
            )}
          </div>

          <button
            onClick={onRefresh}
            disabled={loading}
            className="flex items-center space-x-2 px-3.5 py-1.5 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold shadow-md shadow-sky-600/20 transition disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh Data</span>
          </button>
        </div>

      </div>
    </header>
  );
};
