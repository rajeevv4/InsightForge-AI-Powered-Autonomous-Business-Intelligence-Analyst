import React, { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Menu, Search, Bell, Sparkles } from 'lucide-react';

interface HeaderProps {
  onOpenMobileMenu: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onOpenMobileMenu }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState<string>('');

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

  const page = getPageDetails();

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      navigate('/ask');
    }
  };

  return (
    <header className="sticky top-0 z-20 bg-white/90 backdrop-blur-md border-b border-slate-200/80 px-4 sm:px-6 lg:px-8 py-3.5 transition-all">
      <div className="flex items-center justify-between gap-4">
        
        {/* Left Side: Mobile Toggle & Page Title */}
        <div className="flex items-center space-x-3">
          <button
            onClick={onOpenMobileMenu}
            className="lg:hidden p-2 text-slate-500 hover:text-slate-800 rounded-lg hover:bg-slate-100 transition-colors"
            aria-label="Open navigation menu"
          >
            <Menu className="w-5 h-5" />
          </button>

          <div>
            <h1 className="text-lg sm:text-xl font-bold text-slate-900 tracking-tight">
              {page.title}
            </h1>
            <p className="text-xs text-slate-500 hidden sm:block mt-0.5">
              {page.description}
            </p>
          </div>
        </div>

        {/* Right Side: Global Search, Notifications, User Avatar */}
        <div className="flex items-center space-x-3">
          
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
            <button
              type="submit"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 text-indigo-600 hover:text-indigo-800 rounded-lg transition-colors"
              title="Search or Ask AI"
            >
              <Sparkles className="w-3.5 h-3.5" />
            </button>
          </form>

          {/* Notifications Button */}
          <button
            className="p-2 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-xl border border-slate-200/60 relative transition-colors"
            title="Notifications"
          >
            <Bell className="w-4 h-4" />
            <span className="w-2 h-2 rounded-full bg-indigo-600 absolute top-2 right-2 border-2 border-white" />
          </button>

          {/* User Profile Avatar */}
          <div className="flex items-center space-x-2.5 pl-2 border-l border-slate-200/80">
            <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-600 to-blue-500 text-white font-semibold text-xs flex items-center justify-center shadow-xs">
              RK
            </div>
            <div className="hidden xl:block text-left">
              <span className="block text-xs font-bold text-slate-900 leading-tight">
                Rajeev Karakoti
              </span>
              <span className="block text-[10px] text-slate-500 leading-tight">
                Lead BI Analyst
              </span>
            </div>
          </div>

        </div>

      </div>
    </header>
  );
};
