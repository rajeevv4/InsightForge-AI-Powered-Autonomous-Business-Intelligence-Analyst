import React, { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Menu, Search, Moon, Sun } from 'lucide-react';
import { useUi } from '../../contexts/UiContext';
import { CURRENCY_OPTIONS, CurrencyCode } from '../../lib/format';
import { HealthResponse } from '../../types/api';
import { useActiveDataset } from '../../contexts/ActiveDatasetContext';
import { DatasetSwitcher } from './DatasetSwitcher';

interface HeaderProps {
  onOpenMobileMenu: () => void;
  health?: HealthResponse | null;
}

export const Header: React.FC<HeaderProps> = ({ onOpenMobileMenu, health }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState<string>('');
  const { isOlist, activeDataset } = useActiveDataset();
  const { theme, toggleTheme, currency, setCurrency, canPickCurrency } = useUi();

  const getPageDetails = () => {
    switch (location.pathname) {
      case '/':
        return {
          title: 'Executive Overview',
          description: 'Explore your business performance and discover meaningful insights.'
        };
      case '/ask':
        return {
          title: 'Ask InsightForge',
          description: 'Ask questions about your business data in plain English.'
        };
      case '/analytics':
        return {
          title: 'Business Analytics',
          description: 'Detailed revenue trends, category performance, regional sales, and logistics.'
        };
      case '/customers':
        return {
          title: 'Customers & Geography',
          description: 'Regional purchasing distributions and active customer analytics.'
        };
      case '/products':
        return {
          title: 'Products & Categories',
          description: 'Merchandise sales performance, unit volumes, and category review scores.'
        };
      case '/geography':
        return {
          title: 'Geographic Sales',
          description: 'State-level sales volume, freight costs, and customer density.'
        };
      case '/sellers':
        return {
          title: 'Seller Performance',
          description: 'Merchant order fulfillment rates, product offerings, and ratings.'
        };
      case '/payments':
        return {
          title: 'Payment Analytics',
          description: 'Distribution of payment methods, average order values, and installments.'
        };
      case '/delivery':
        return {
          title: 'Delivery SLA',
          description: 'Logistics SLA compliance, on-time delivery rates, and average delay days.'
        };
      case '/data-quality':
        return {
          title: 'Data Quality',
          description: 'Monitor the reliability and completeness of data used by InsightForge.'
        };
      case '/anomalies':
        return {
          title: 'Statistical Anomalies',
          description: 'Deterministic outlier detection across e-commerce time series and business dimensions.'
        };
      case '/report':
        return {
          title: 'Report',
          description: 'One-click report: summary, KPIs, trend, breakdowns, anomaly drivers, forecast and data quality, with PDF download.'
        };
      case '/forecast':
        return {
          title: 'Forecast',
          description: 'Baseline forecast with 80% / 95% confidence bands and a backtest against a naive baseline.'
        };
      case '/datasets':
        return {
          title: 'Dataset Workspace',
          description: 'Upload tabular files (CSV, TSV, XLSX) into isolated schemas with deterministic zero-LLM profiling.'
        };
      case '/settings':
        return {
          title: 'Settings',
          description: 'Manage your InsightForge workspace preferences and configuration.'
        };
      case '/help':
        return {
          title: 'Help & Information',
          description: 'Documentation, system guide, and support resources.'
        };
      default:
        return {
          title: 'Dashboard',
          description: 'AI-Powered Business Intelligence Analyst'
        };
    }
  };

  // Uploaded datasets: neutral titles (the Olist texts mention states, freight, sellers...).
  const getCustomPageDetails = (): { title: string; description: string } | null => {
    const name = activeDataset?.name || 'your dataset';
    const path = location.pathname;
    if (path.startsWith('/tables/')) {
      const table = decodeURIComponent(path.slice('/tables/'.length));
      return { title: `Table: ${table.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}`, description: `Analysis of the ${table} table in ${name}.` };
    }
    const generic: Record<string, { title: string; description: string }> = {
      '/': { title: 'Overview', description: `Key metrics and trends for ${name}.` },
      '/analytics': { title: 'Analytics', description: `Measures, trends and breakdowns for ${name}.` },
      '/customers': { title: 'Customers', description: 'This Olist page is not part of the uploaded dataset view.' },
      '/products': { title: 'Products', description: 'This Olist page is not part of the uploaded dataset view.' },
      '/geography': { title: 'Geography', description: `Location-based breakdowns for ${name}.` },
      '/sellers': { title: 'Sellers', description: `Seller / vendor breakdowns for ${name}.` },
      '/payments': { title: 'Payments', description: `Payment method breakdowns for ${name}.` },
      '/delivery': { title: 'Delivery', description: `Delivery and shipping metrics for ${name}.` },
      '/data-quality': { title: 'Data Quality', description: `Deterministic data checks for ${name}.` },
      '/anomalies': { title: 'Anomalies', description: `Statistical outliers in ${name}.` },
      '/forecast': { title: 'Forecast', description: `Baseline forecast with confidence bands for ${name}.` },
      '/report': { title: 'Report', description: `One-click report with PDF download for ${name}.` },
    };
    return generic[path] || null;
  };

  const page = (!isOlist && getCustomPageDetails()) || getPageDetails();

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = searchQuery.trim();
    if (q) {
      // Hand the question to AskInsightForge, which submits it on arrival.
      navigate('/ask', { state: { question: q } });
      setSearchQuery('');
    }
  };

  return (
    <header className="sticky top-0 z-30 bg-white/70 backdrop-blur-xl backdrop-saturate-150 border-b border-slate-200/80 px-4 sm:px-6 lg:px-8 py-3 transition-all">
      <div className="flex items-center justify-between gap-3">
        
        {/* Left Side: Mobile Toggle & Page Title */}
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <button
            onClick={onOpenMobileMenu}
            className="lg:hidden p-2 text-slate-500 hover:text-slate-800 rounded-lg hover:bg-slate-100 transition-colors"
            aria-label="Open navigation menu"
          >
            <Menu className="w-5 h-5" />
          </button>

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 min-w-0">
              <h1 className="text-lg sm:text-xl font-bold text-slate-900 tracking-tight truncate max-w-full" title={page.title}>
                {page.title}
              </h1>
              {/* Active dataset for the whole app (replaces the old hardcoded "Demo dataset" badge) */}
              <DatasetSwitcher />
              {health?.data_source === 'fixture' && (
                <span
                  className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-amber-100 text-amber-800 border border-amber-300 shadow-xs"
                  title="Database is unreachable; operating in offline fixture mode"
                >
                  DEMO DATA
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 hidden sm:block mt-0.5 truncate" title={page.description}>
              {page.description}
            </p>
          </div>
        </div>

        {/* Right Side: Theme, Currency, Global Search, Notifications, User Avatar */}
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          {canPickCurrency && (
            <label className="flex items-center gap-1 text-[11px] text-slate-500" title="Currency for money measures of this dataset (saved in this browser)">
              <span className="hidden lg:inline">Currency</span>
              <select
                aria-label="Currency for this dataset"
                value={currency}
                onChange={(e) => setCurrency(e.target.value as CurrencyCode)}
                className="text-xs border border-slate-200 rounded-lg px-1.5 py-1.5 bg-white cursor-pointer"
              >
                {CURRENCY_OPTIONS.map((c) => <option key={c.label} value={c.code}>{c.label}</option>)}
              </select>
            </label>
          )}
          <button
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
            className="p-2 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-xl border border-slate-200/60 transition-colors cursor-pointer"
          >
            {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
          
          {/* Interactive Global Search Input */}
          <form onSubmit={handleSearchSubmit} className="hidden md:flex items-center relative">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search metrics, charts, or ask anything..."
              className="w-64 lg:w-80 bg-slate-100/70 border border-slate-200 rounded-xl pl-9 pr-8 py-2 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500 transition-all"
            />
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          </form>

          {/* User Profile Avatar */}
          <div className="hidden sm:flex items-center space-x-2.5 pl-2 border-l border-slate-200/80">
            <div className="w-8 h-8 rounded-full bg-brand-gradient text-white font-semibold text-xs flex items-center justify-center shadow-xs">
              IF
            </div>
            <div className="hidden xl:block text-left">
              <span className="block text-xs font-bold text-slate-900 leading-tight">
                InsightForge Team
              </span>
              <span className="block text-[10px] text-slate-500 leading-tight">
                Analytics Workspace
              </span>
            </div>
          </div>


        </div>

      </div>
    </header>
  );
};
