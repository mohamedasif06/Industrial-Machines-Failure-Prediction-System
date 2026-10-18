import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { AppShell } from './layouts/AppShell';
import { AlertsNotifications } from './pages/AlertsNotifications';
import { LiveMachineMonitoring } from './pages/LiveMachineMonitoring';
import { OperationsOverview } from './pages/OperationsOverview';
import { PredictionAnalysis } from './pages/PredictionAnalysis';
import { TelemetryProvider } from './hooks/TelemetryProvider';
import { AuthProvider } from './hooks/AuthProvider';
import { LoginPage } from './pages/LoginPage';
import { SignupPage } from './pages/SignupPage';
import { useAuth } from './services/auth';

function AuthGate() {
  const { state } = useAuth();
  const location = useLocation();
  if (state.loading) return <main className="login-page"><p className="login-loading">Checking secure session…</p></main>;
  if (state.user === null) {
    if (location.pathname === '/signup') return <SignupPage />;
    return location.pathname === '/login' ? <LoginPage /> : <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (location.pathname === '/login' || location.pathname === '/signup') return <Navigate to="/" replace />;
  return <TelemetryProvider><Routes>
    <Route element={<AppShell />}>
      <Route index element={<OperationsOverview />} />
      <Route path="monitoring" element={<LiveMachineMonitoring />} />
      <Route path="analysis" element={<PredictionAnalysis />} />
      <Route path="alerts" element={<AlertsNotifications />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Route>
  </Routes></TelemetryProvider>;
}

export function App() {
  return <AuthProvider><AuthGate /></AuthProvider>;
}
