import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppLayout } from './layouts/AppLayout';
import { OverviewPage } from './pages/OverviewPage';
import { AskPage } from './pages/AskPage';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { DataQualityPage } from './pages/DataQualityPage';
import { SettingsPage } from './pages/SettingsPage';
import { HelpPage } from './pages/HelpPage';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppLayout />}>
          <Route index element={<OverviewPage />} />
          <Route path="ask" element={<AskPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="customers" element={<AnalyticsPage initialTab="geography" />} />
          <Route path="products" element={<AnalyticsPage initialTab="products" />} />
          <Route path="geography" element={<AnalyticsPage initialTab="geography" />} />
          <Route path="sellers" element={<AnalyticsPage initialTab="sellers" />} />
          <Route path="payments" element={<AnalyticsPage initialTab="payments" />} />
          <Route path="delivery" element={<AnalyticsPage initialTab="delivery" />} />
          <Route path="data-quality" element={<DataQualityPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="help" element={<HelpPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
};

export default App;
