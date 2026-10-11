import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from './layouts/AppShell';
import { AlertsNotifications } from './pages/AlertsNotifications';
import { LiveMachineMonitoring } from './pages/LiveMachineMonitoring';
import { OperationsOverview } from './pages/OperationsOverview';
import { PredictionAnalysis } from './pages/PredictionAnalysis';
import { TelemetryProvider } from './hooks/TelemetryProvider';

export function App() {
  return (
    <TelemetryProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<OperationsOverview />} />
          <Route path="monitoring" element={<LiveMachineMonitoring />} />
          <Route path="analysis" element={<PredictionAnalysis />} />
          <Route path="alerts" element={<AlertsNotifications />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </TelemetryProvider>
  );
}
