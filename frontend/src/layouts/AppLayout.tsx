import React, { useState, useEffect, useCallback } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { FirstVisitTour } from '../components/ui';
import { Sidebar } from '../components/navigation/Sidebar';
import { Header } from '../components/navigation/Header';
import { api } from '../services/api';
import { HealthResponse } from '../types/api';

export interface LayoutContextType {
  health: HealthResponse | null;
  globalLoading: boolean;
  refreshData: () => void;
}

export const AppLayout: React.FC = () => {
  const [mobileOpen, setMobileOpen] = useState<boolean>(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [globalLoading, setGlobalLoading] = useState<boolean>(false);
  const [refreshTrigger, setRefreshTrigger] = useState<number>(0);
  const location = useLocation();

  const fetchHealth = useCallback(async () => {
    setGlobalLoading(true);
    try {
      const data = await api.getHealth();
      setHealth(data);
    } catch (err) {
      setHealth({
        status: 'unhealthy',
        database: 'disconnected',
        data_source: 'postgres',
        service: 'InsightForge',
        version: '0.1.0',
      });
    } finally {
      setGlobalLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  const handleRefresh = () => {
    fetchHealth();
    setRefreshTrigger((prev) => prev + 1);
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 flex antialiased font-sans relative overflow-x-clip">
      {/* Soft gradient wash behind the content (decorative) */}
      <div aria-hidden="true" className="pointer-events-none fixed inset-x-0 top-0 h-80 bg-gradient-to-b from-indigo-100/70 via-violet-50/40 to-transparent dark:from-indigo-500/10 dark:via-violet-500/5 dark:to-transparent -z-0" />
      <a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[90] focus:bg-white focus:px-3 focus:py-2 focus:rounded-lg focus:shadow-lift text-sm">Skip to content</a>
      {/* Sidebar Navigation */}
      <Sidebar mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} />

      {/* Main Content Container */}
      <div className="flex-1 flex flex-col min-w-0 lg:pl-64 relative">
        {/* Top Header */}
        <Header
          onOpenMobileMenu={() => setMobileOpen(true)}
          health={health}
        />

        {/* Page Content View */}
        <main id="main-content" className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 min-w-0">
          {/* Page transition: re-mounts the wrapper (not the page state) on route change */}
          <div key={location.pathname} className="page-enter">
            <Outlet context={{ health, globalLoading, refreshData: handleRefresh, refreshTrigger }} />
          </div>
        </main>
        <FirstVisitTour />
      </div>
    </div>
  );
};
