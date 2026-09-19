import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Sparkles,
  BarChart3,
  ShieldCheck,
  Lightbulb,
  Settings,
  X,
  Zap
} from 'lucide-react';

interface SidebarProps {
  mobileOpen: boolean;
  setMobileOpen: (open: boolean) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ mobileOpen, setMobileOpen }) => {
  const location = useLocation();

  const navItems = [
    {
      name: 'Overview',
      path: '/',
      icon: LayoutDashboard,
      disabled: false,
    },
    {
      name: 'Ask InsightForge',
      path: '/ask',
      icon: Sparkles,
      disabled: false,
      badge: 'AI',
    },
    {
      name: 'Analytics',
      path: '/analytics',
      icon: BarChart3,
      disabled: false,
    },
    {
      name: 'Data Quality',
      path: '/data-quality',
      icon: ShieldCheck,
      disabled: false,
    },
    {
      name: 'Insights',
      path: '#',
      icon: Lightbulb,
      disabled: true,
      badge: 'Soon',
    },
    {
      name: 'Settings',
      path: '#',
      icon: Settings,
      disabled: true,
      badge: 'Soon',
    },
  ];

  const sidebarContent = (
    <div className="flex flex-col h-full bg-slate-950 border-r border-slate-800 text-slate-100 w-64 select-none">
      {/* Brand Logo Header */}
      <div className="h-16 flex items-center justify-between px-5 border-b border-slate-800/80">
        <NavLink to="/" className="flex items-center space-x-3 group" onClick={() => setMobileOpen(false)}>
          <div className="p-2 bg-gradient-to-tr from-cyan-500 to-blue-600 rounded-xl shadow-lg shadow-cyan-500/20 group-hover:scale-105 transition-transform">
            <Zap className="w-5 h-5 text-white" />
          </div>
          <div>
            <span className="font-extrabold text-base tracking-tight text-white group-hover:text-cyan-400 transition-colors">
              InsightForge
            </span>
            <span className="block text-[10px] text-slate-400 font-mono tracking-wider uppercase">
              BI Analyst
            </span>
          </div>
        </NavLink>

        {/* Mobile Close Button */}
        <button
          onClick={() => setMobileOpen(false)}
          className="lg:hidden text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
          aria-label="Close navigation sidebar"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Main Navigation Links */}
      <div className="flex-1 py-6 px-3 space-y-1.5 overflow-y-auto">
        <div className="px-3 pb-2 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
          Main Navigation
        </div>

        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive =
            item.path === '/'
              ? location.pathname === '/'
              : location.pathname.startsWith(item.path) && item.path !== '#';

          if (item.disabled) {
            return (
              <div
                key={item.name}
                className="flex items-center justify-between px-3 py-2.5 rounded-xl text-slate-600 cursor-not-allowed opacity-60"
              >
                <div className="flex items-center space-x-3">
                  <Icon className="w-4 h-4 text-slate-600" />
                  <span className="text-sm font-medium">{item.name}</span>
                </div>
                {item.badge && (
                  <span className="text-[10px] bg-slate-800 text-slate-500 px-2 py-0.5 rounded font-mono font-medium">
                    {item.badge}
                  </span>
                )}
              </div>
            );
          }

          return (
            <NavLink
              key={item.name}
              to={item.path}
              onClick={() => setMobileOpen(false)}
              className={`flex items-center justify-between px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                isActive
                  ? 'bg-slate-900 text-cyan-400 border border-slate-800 shadow-md shadow-cyan-950/20'
                  : 'text-slate-400 hover:text-slate-100 hover:bg-slate-900/60'
              }`}
            >
              <div className="flex items-center space-x-3">
                <Icon
                  className={`w-4 h-4 transition-colors ${
                    isActive ? 'text-cyan-400' : 'text-slate-400 group-hover:text-slate-300'
                  }`}
                />
                <span>{item.name}</span>
              </div>
              {item.badge && (
                <span
                  className={`text-[10px] px-2 py-0.5 rounded font-mono font-semibold ${
                    isActive
                      ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                      : 'bg-slate-800 text-slate-400'
                  }`}
                >
                  {item.badge}
                </span>
              )}
            </NavLink>
          );
        })}
      </div>

      {/* Footer Info */}
      <div className="p-4 border-t border-slate-800/80 bg-slate-950/60 text-xs text-slate-400 font-mono">
        <div className="flex items-center justify-between">
          <span>Engine Status</span>
          <span className="text-emerald-400 flex items-center gap-1 font-semibold">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            Online
          </span>
        </div>
        <div className="text-[10px] text-slate-500 mt-1">Olist E-Commerce Analytics</div>
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
          className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-40 lg:hidden"
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
