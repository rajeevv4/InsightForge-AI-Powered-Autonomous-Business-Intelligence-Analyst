import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppLayout } from './layouts/AppLayout';
import { OverviewPage } from './pages/OverviewPage';
import { AskPage } from './pages/AskPage';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { DataQualityPage } from './pages/DataQualityPage';
import { AnomaliesPage } from './pages/AnomaliesPage';
import { ForecastPage } from './pages/ForecastPage';
import { ReportPage } from './pages/ReportPage';
import { BoardPage } from './pages/BoardPage';
import { DatasetsPage } from './pages/DatasetsPage';
import { SettingsPage } from './pages/SettingsPage';
import { HelpPage } from './pages/HelpPage';
import { ActiveDatasetProvider, DatasetAware } from './contexts/ActiveDatasetContext';
import { UiProvider } from './contexts/UiContext';
import { CustomPagePlaceholder } from './components/workspace/CustomPagePlaceholder';
import { CustomOverview } from './components/workspace/CustomOverview';
import { CustomAnalytics } from './components/workspace/CustomAnalytics';
import { CustomGroupPage, CustomTablePage } from './components/workspace/CustomTablePage';
import { CustomDataQuality } from './components/workspace/CustomDataQuality';
import { CustomAnomalies } from './components/workspace/CustomAnomalies';

/*
 * Dataset-aware routing: each Olist route renders the unchanged Olist page when the
 * Olist demo is active, or the uploaded-dataset page otherwise (switch happens here,
 * so the Olist page files themselves are untouched).
 */
export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <ActiveDatasetProvider>
      <UiProvider>
        <Routes>
          <Route path="/" element={<AppLayout />}>
            <Route index element={<DatasetAware olist={<OverviewPage />} custom={<CustomOverview />} />} />
            <Route path="ask" element={<AskPage />} />
            <Route path="board" element={<BoardPage />} />
            <Route path="analytics" element={<DatasetAware olist={<AnalyticsPage />} custom={<CustomAnalytics />} />} />
            <Route path="customers" element={<DatasetAware olist={<AnalyticsPage initialTab="geography" />} custom={<CustomPagePlaceholder page="Customers" olistOnly />} />} />
            <Route path="products" element={<DatasetAware olist={<AnalyticsPage initialTab="products" />} custom={<CustomPagePlaceholder page="Products" olistOnly />} />} />
            <Route path="geography" element={<DatasetAware olist={<AnalyticsPage initialTab="geography" />} custom={<CustomGroupPage key="geography" group="geography" />} />} />
            <Route path="sellers" element={<DatasetAware olist={<AnalyticsPage initialTab="sellers" />} custom={<CustomGroupPage key="sellers" group="sellers" />} />} />
            <Route path="payments" element={<DatasetAware olist={<AnalyticsPage initialTab="payments" />} custom={<CustomGroupPage key="payments" group="payments" />} />} />
            <Route path="delivery" element={<DatasetAware olist={<AnalyticsPage initialTab="delivery" />} custom={<CustomGroupPage key="delivery" group="delivery" />} />} />
            <Route path="data-quality" element={<DatasetAware olist={<DataQualityPage />} custom={<CustomDataQuality />} />} />
            <Route path="anomalies" element={<DatasetAware olist={<AnomaliesPage />} custom={<CustomAnomalies />} />} />
            <Route path="forecast" element={<DatasetAware olist={<ForecastPage key="olist" />} custom={<ForecastPage key="custom" />} />} />
            <Route path="report" element={<DatasetAware olist={<ReportPage key="olist" />} custom={<ReportPage key="custom" />} />} />
            {/* Table pages exist only for uploaded datasets */}
            <Route path="tables/:tableName" element={<DatasetAware olist={<Navigate to="/" replace />} custom={<CustomTablePage />} />} />
            <Route path="datasets" element={<DatasetsPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="help" element={<HelpPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </UiProvider>
      </ActiveDatasetProvider>
    </BrowserRouter>
  );
};

export default App;
