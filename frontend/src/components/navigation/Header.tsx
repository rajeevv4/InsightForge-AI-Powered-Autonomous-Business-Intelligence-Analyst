import React from 'react';
import { useLocation } from 'react-router-dom';
import { Menu, RefreshCw, Database, Server } from 'lucide-react';
import { HealthResponse } from '../../types/api';

interface HeaderProps {
  health: HealthResponse | null;
  loading: boolean;
  onRefresh: () => void;
  onOpenMobileMenu: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  health,
  loading,
  onRefresh,
  onOpenMobileMenu
}) => {
  const location = useLocation();

  const getPageDetails = () => {
    switch (location.pathname) {
      case '/':
        return {
          title: 'Executive Overview',
          description: 'High-level business metrics and key performance indicators.'
        };
      case '/ask':
        return {
          title: 'Ask InsightForge',
          description: 'Ask business questions in natural language grounded in PostgreSQL data.'
        };
      case '/analytics':
        return {
          title: 'Business Analytics',
          description: 'Detailed revenue trends, category performance, regional sales, and logistics.'
        };
      case '/data-quality':
        return {
          title: 'Data Quality & Audit',
          description: 'Monitor database integrity, missing values, PK/FK rules, and audit status.'
        };
      default:
        return {
          title: 'Dashboard',
          description: 'AI-Powered Business Intelligence Analyst'
        };
    }
  };

  const page = getPageDetails();
  const isDbConnected = health?.database === 'connected' || health?.status === 'healthy';

  return (
    <header className="sticky top-0 z-20 bg-slate-950/90 backdrop-blur-md border-b border-slate-800 px-4 sm:px-6 lg:px-8 py-3.5 transition-all">
      <div className="flex items-center justify-between gap-4">
        
        {/* Left Side: Mobile Menu Button & Page Title */}
        <div className="flex items-center space-x-3">
          <button
            onClick={onOpenMobileMenu}
            className="lg:hidden p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
            aria-label="Open navigation menu"
          >
            <Menu className="w-5 h-5" />
          </button>

          <div>
            <h1 className="text-lg sm:text-xl font-bold text-white tracking-tight flex items-center gap-2">
              {page.title}
            </h1>
            <p className="text-xs text-slate-400 hidden sm:block mt-0.5">
              {page.description}
            </p>
          </div>
        </div>

        {/* Right Side: Status Badges & Refresh Action */}
        <div className="flex items-center space-x-3">
          
          {/* PostgreSQL Connectivity Badge */}
          <div className="hidden sm:flex items-center space-x-2 bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-lg text-xs font-mono">
            <Database className={`w-3.5 h-3.5 ${isDbConnected ? 'text-emerald-400' : 'text-amber-400'}`} />
            <span className="text-slate-400">PostgreSQL</span>
            <span className={`w-2 h-2 rounded-full ${isDbConnected ? 'bg-emerald-400' : 'bg-amber-400'}`} />
          </div>

          {/* Refresh Data Button */}
          <button
            onClick={onRefresh}
            disabled={loading}
            className="flex items-center space-x-2 bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-800 hover:border-slate-700 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all disabled:opacity-50 active:scale-95 shadow-sm"
            title="Refresh current page analytics data"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-cyan-400 ${loading ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">Refresh Data</span>
          </button>
        </div>

      </div>
    </header>
  );
};
