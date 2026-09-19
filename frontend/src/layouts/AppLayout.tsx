import React, { useState, useEffect, useCallback } from 'react';
import { Outlet } from 'react-router-dom';
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

  const fetchHealth = useCallback(async () => {
    setGlobalLoading(true);
    try {
      const data = await api.getHealth();
      setHealth(data);
    } catch (err) {
      setHealth({
        status: 'degraded',
        database: 'disconnected',
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
    <div className="min-h-screen bg-slate-950 text-slate-100 flex">
      {/* Sidebar Navigation */}
      <Sidebar mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 lg:pl-64">
        {/* Top Header */}
        <Header
          health={health}
          loading={globalLoading}
          onRefresh={handleRefresh}
          onOpenMobileMenu={() => setMobileOpen(true)}
        />

        {/* Page Content */}
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <Outlet context={{ health, globalLoading, refreshData: handleRefresh, refreshTrigger }} />
        </main>
      </div>
    </div>
  );
};
