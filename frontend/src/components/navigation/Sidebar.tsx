import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
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
  Settings,
  HelpCircle,
  X,
  Layers
} from 'lucide-react';

interface SidebarProps {
  mobileOpen: boolean;
  setMobileOpen: (open: boolean) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ mobileOpen, setMobileOpen }) => {
  const location = useLocation();

  const mainNavItems = [
    { name: 'Overview', path: '/', icon: LayoutDashboard },
    { name: 'Ask InsightForge', path: '/ask', icon: Sparkles },
    { name: 'Analytics', path: '/analytics', icon: BarChart3 },
    { name: 'Customers', path: '/customers', icon: Users },
    { name: 'Products', path: '/products', icon: ShoppingBag },
    { name: 'Geography', path: '/geography', icon: MapPin },
    { name: 'Sellers', path: '/sellers', icon: Store },
    { name: 'Payments', path: '/payments', icon: CreditCard },
    { name: 'Delivery', path: '/delivery', icon: Truck },
    { name: 'Data Quality', path: '/data-quality', icon: ShieldCheck },
  ];

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
          <div className="w-9 h-9 bg-indigo-600 rounded-xl flex items-center justify-center text-white shadow-sm group-hover:bg-indigo-700 transition-colors">
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
      <div className="flex-1 py-5 px-3 space-y-1 overflow-y-auto">
        <div className="px-3 pb-2 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
          Workspace Navigation
        </div>

        {mainNavItems.map((item) => {
          const Icon = item.icon;
          const active = isItemActive(item.path);

          return (
            <NavLink
              key={item.name}
              to={item.path}
              onClick={() => setMobileOpen(false)}
              className={`flex items-center space-x-3 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all ${
                active
                  ? 'bg-indigo-50/80 text-indigo-600 font-semibold border-r-2 border-indigo-600 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70'
              }`}
            >
              <Icon
                className={`w-4 h-4 transition-colors ${
                  active ? 'text-indigo-600' : 'text-slate-400 group-hover:text-slate-600'
                }`}
              />
              <span>{item.name}</span>
            </NavLink>
          );
        })}
      </div>

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
              className={`flex items-center space-x-3 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all ${
                active
                  ? 'bg-indigo-50/80 text-indigo-600 font-semibold border-r-2 border-indigo-600'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70'
              }`}
            >
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
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-40 lg:hidden"
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
