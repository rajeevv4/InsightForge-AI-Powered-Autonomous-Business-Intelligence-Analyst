import React, { useEffect, useRef, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { useActiveDataset } from '../../contexts/ActiveDatasetContext';
import { api } from '../../services/api';
import { DatasetNavigationResponse } from '../../types/api';
import {
  LayoutDashboard,
  Sparkles,
  BarChart3,
  Users,
  ShoppingBag,
  MapPin,
  Store,
  CreditCard,
  Truck,
  ShieldCheck,
  AlertOctagon,
  Settings,
  HelpCircle,
  X,
  Layers,
  Database,
  Table2,
  LineChart,
  FileText
} from 'lucide-react';

interface SidebarProps {
  mobileOpen: boolean;
  setMobileOpen: (open: boolean) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ mobileOpen, setMobileOpen }) => {
  const location = useLocation();

  const mainNavItems = [
    { name: 'Overview', path: '/', icon: LayoutDashboard },
    { name: 'Datasets', path: '/datasets', icon: Database },
    { name: 'Ask InsightForge', path: '/ask', icon: Sparkles },
    { name: 'Analytics', path: '/analytics', icon: BarChart3 },
    { name: 'Customers', path: '/customers', icon: Users },
    { name: 'Products', path: '/products', icon: ShoppingBag },
    { name: 'Geography', path: '/geography', icon: MapPin },
    { name: 'Sellers', path: '/sellers', icon: Store },
    { name: 'Payments', path: '/payments', icon: CreditCard },
    { name: 'Delivery', path: '/delivery', icon: Truck },
    { name: 'Data Quality', path: '/data-quality', icon: ShieldCheck },
    { name: 'Anomalies', path: '/anomalies', icon: AlertOctagon },
    { name: 'Forecast', path: '/forecast', icon: LineChart },
    { name: 'Report', path: '/report', icon: FileText },
  ];

  // ---- Uploaded dataset: items come from GET /api/datasets/{id}/navigation ----
  const { isOlist, activeReady, activeDatasetId, activeDataset } = useActiveDataset();
  const [customNav, setCustomNav] = useState<DatasetNavigationResponse | null>(null);
  const [navLoading, setNavLoading] = useState(false);
  const [navError, setNavError] = useState<string | null>(null);
  const navRequestRef = useRef<string>('');

  useEffect(() => {
    // Wait until the stored dataset is confirmed to exist (avoids 404s for stale ids).
    if (isOlist || !activeReady) return;
    const id = activeDatasetId;
    navRequestRef.current = id;
    setCustomNav(null);
    setNavError(null);
    setNavLoading(true);
    api
      .getDatasetNavigation(id)
      .then((nav) => {
        if (navRequestRef.current === id) setCustomNav(nav);
      })
      .catch((err: any) => {
        if (navRequestRef.current !== id) return;
        const status = err?.response?.status;
        setNavError(
          status === 429
            ? 'Too many requests; try again shortly.'
            : err?.response?.data?.detail || 'Could not load dataset sections.'
        );
      })
      .finally(() => {
        if (navRequestRef.current === id) setNavLoading(false);
      });
  }, [isOlist, activeReady, activeDatasetId]);

  const CORE_KEYS_BEFORE = ['overview', 'datasets', 'ask', 'analytics'];
  const CORE_KEYS_AFTER = ['data_quality', 'anomalies', 'forecast', 'report'];
  const CORE_FALLBACK: Record<string, { name: string; path: string }> = {
    overview: { name: 'Overview', path: '/' },
    datasets: { name: 'Datasets', path: '/datasets' },
    ask: { name: 'Ask InsightForge', path: '/ask' },
    analytics: { name: 'Analytics', path: '/analytics' },
    data_quality: { name: 'Data Quality', path: '/data-quality' },
    anomalies: { name: 'Anomalies', path: '/anomalies' },
    forecast: { name: 'Forecast', path: '/forecast' },
    report: { name: 'Report', path: '/report' },
  };
  const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
    overview: LayoutDashboard,
    datasets: Database,
    ask: Sparkles,
    analytics: BarChart3,
    geography: MapPin,
    sellers: Store,
    payments: CreditCard,
    delivery: Truck,
    data_quality: ShieldCheck,
    anomalies: AlertOctagon,
    forecast: LineChart,
    report: FileText,
  };
  const iconFor = (key: string) => (key.startsWith('table:') ? Table2 : ICONS[key] || Layers);

  // While loading (or on error) the always-present core items are shown immediately.
  const customNavItems: { name: string; path: string; icon: React.ComponentType<{ className?: string }> }[] = customNav
    ? customNav.items.map((i) => ({ name: i.label, path: i.path, icon: iconFor(i.key) }))
    : [...CORE_KEYS_BEFORE, ...CORE_KEYS_AFTER].map((k) => ({ ...CORE_FALLBACK[k], icon: iconFor(k) }));

  const navItems = isOlist ? mainNavItems : customNavItems;

  const bottomNavItems = [
    { name: 'Settings', path: '/settings', icon: Settings },
    { name: 'Help & Info', path: '/help', icon: HelpCircle },
  ];

  const isItemActive = (path: string) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname === path || (path !== '/' && location.pathname.startsWith(path));
  };

  const sidebarContent = (
    <div className="flex flex-col h-full bg-white border-r border-slate-200/80 text-slate-700 w-64 select-none">
      {/* Brand Header */}
      <div className="h-16 flex items-center justify-between px-5 border-b border-slate-100">
        <NavLink
          to="/"
          className="flex items-center space-x-3 group"
          onClick={() => setMobileOpen(false)}
        >
          {/* Abstract I/F Geometric Data Emblem */}
          <div className="w-9 h-9 bg-brand-gradient rounded-xl flex items-center justify-center text-white shadow-glow group-hover:scale-105 transition-transform">
            <svg
              className="w-5 h-5 fill-current"
              viewBox="0 0 24 24"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path d="M4 4h4v16H4V4zm6 6h4v10h-4V10zm6-4h4v14h-4V6z" />
            </svg>
          </div>
          <div>
            <span className="font-extrabold text-base tracking-tight text-slate-900 group-hover:text-indigo-600 transition-colors">
              InsightForge
            </span>
            <span className="block text-[11px] text-slate-500 font-medium tracking-normal">
              AI Business Analyst
            </span>
          </div>
        </NavLink>

        {/* Mobile Close Button */}
        <button
          onClick={() => setMobileOpen(false)}
          className="lg:hidden text-slate-400 hover:text-slate-700 p-1.5 rounded-lg hover:bg-slate-100"
          aria-label="Close navigation sidebar"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Main Navigation Links */}
      <nav aria-label="Workspace navigation" className="flex-1 py-5 px-3 space-y-1 overflow-y-auto">
        <div className="px-3 pb-2 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
          Workspace Navigation
        </div>
        {!isOlist && (
          <div className="px-3 pb-2 -mt-1 text-[10px] text-indigo-600 font-medium truncate" title={activeDataset?.name}>
            {activeDataset?.name || 'Uploaded dataset'}
          </div>
        )}

        {navItems.map((item) => {
          const Icon = item.icon;
          const active = isItemActive(item.path);

          return (
            <NavLink
              key={item.name}
              to={item.path}
              onClick={() => setMobileOpen(false)}
              aria-current={active ? 'page' : undefined}
              className={`group relative flex items-center space-x-3 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-200 ${
                active
                  ? 'bg-indigo-50/80 text-indigo-600 font-semibold shadow-xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70 hover:translate-x-0.5'
              }`}
            >
              {/* Animated active indicator */}
              <span aria-hidden="true" className={`absolute left-0 top-1/2 -translate-y-1/2 h-5 w-1 rounded-r-full bg-brand-gradient transition-transform duration-300 origin-center ${active ? 'scale-y-100' : 'scale-y-0'}`} />
              <Icon
                className={`w-4 h-4 transition-colors ${
                  active ? 'text-indigo-600' : 'text-slate-400 group-hover:text-slate-600'
                }`}
              />
              <span className="truncate" title={item.name}>{item.name}</span>
            </NavLink>
          );
        })}

        {!isOlist && navLoading && (
          <div className="px-3.5 py-2 space-y-2" aria-label="Loading dataset sections">
            <div className="h-3 w-28 bg-slate-100 rounded animate-pulse" />
            <div className="h-3 w-20 bg-slate-100 rounded animate-pulse" />
            <div className="h-3 w-24 bg-slate-100 rounded animate-pulse" />
          </div>
        )}
        {!isOlist && navError && (
          <div className="mx-3 mt-2 p-2 rounded-lg bg-amber-50 border border-amber-200 text-[10px] text-amber-800">
            {navError}
          </div>
        )}
      </nav>

      {/* Bottom Navigation Section */}
      <div className="p-3 border-t border-slate-100 space-y-1 bg-slate-50/50">
        <div className="px-3 pb-1.5 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
          System & Support
        </div>
        {bottomNavItems.map((item) => {
          const Icon = item.icon;
          const active = isItemActive(item.path);

          return (
            <NavLink
              key={item.name}
              to={item.path}
              onClick={() => setMobileOpen(false)}
              aria-current={active ? 'page' : undefined}
              className={`group relative flex items-center space-x-3 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-200 ${
                active
                  ? 'bg-indigo-50/80 text-indigo-600 font-semibold'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70 hover:translate-x-0.5'
              }`}
            >
              <span aria-hidden="true" className={`absolute left-0 top-1/2 -translate-y-1/2 h-5 w-1 rounded-r-full bg-brand-gradient transition-transform duration-300 ${active ? 'scale-y-100' : 'scale-y-0'}`} />
              <Icon
                className={`w-4 h-4 ${
                  active ? 'text-indigo-600' : 'text-slate-400'
                }`}
              />
              <span>{item.name}</span>
            </NavLink>
          );
        })}
      </div>
    </div>
  );

  return (
    <>
      {/* Permanent Desktop Sidebar */}
      <aside className="hidden lg:block fixed inset-y-0 left-0 z-30">
        {sidebarContent}
      </aside>

      {/* Mobile Backdrop Overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-40 lg:hidden animate-fade-in"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Mobile Slide-over Drawer */}
      <div
        className={`fixed inset-y-0 left-0 z-50 transform transition-transform duration-300 ease-in-out lg:hidden ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {sidebarContent}
      </div>
    </>
  );
};
