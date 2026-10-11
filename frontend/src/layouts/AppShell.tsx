import { useState } from 'react';
import { Activity, Bell, ChartNoAxesCombined, ChevronRight, LayoutDashboard, Menu, Play, Radio, Square, X } from 'lucide-react';
import { NavLink, Outlet } from 'react-router-dom';
import { useTelemetry } from '../hooks/useTelemetry';
import { SimulatedBadge } from '../components/StatusBadge';
import type { SimulationMode } from '../types/telemetry';

const navigation = [
  { to: '/', label: 'Operations Overview', Icon: LayoutDashboard, end: true },
  { to: '/monitoring', label: 'Live Machine Monitoring', Icon: Radio },
  { to: '/analysis', label: 'Failure Prediction & Analysis', Icon: ChartNoAxesCombined },
  { to: '/alerts', label: 'Alerts & Notifications', Icon: Bell },
];

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [selectedMode, setSelectedMode] = useState<SimulationMode>('normal');
  const [machineCount, setMachineCount] = useState(3);
  const {
    events, loading, error, activeAlertCount, connectionState, isStale, simulatorStatus, simulatorBusy,
    simulatorError, startSimulator, stopSimulator,
  } = useTelemetry();
  const connectionLabel = connectionState[0].toUpperCase() + connectionState.slice(1);
  const activeModeLabel = simulatorStatus?.mode === 'fault_scenario' ? 'Fault Scenario' : simulatorStatus?.mode === 'mixed' ? 'Mixed' : 'Normal';
  const startLabel = selectedMode === 'fault_scenario' ? 'Start Fault Scenario' : selectedMode === 'mixed' ? 'Start Mixed Simulation' : 'Start Normal Simulation';

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      {mobileOpen && <button aria-label="Close navigation" className="mobile-backdrop" onClick={() => setMobileOpen(false)} />}
      <aside className={`sidebar ${mobileOpen ? 'sidebar-open' : ''}`} aria-label="Main navigation">
        <div className="brand"><span className="brand-mark"><Activity size={22} /></span><div><strong>Industrial</strong><span>Failure forecasting</span></div><button className="mobile-close" aria-label="Close menu" onClick={() => setMobileOpen(false)}><X size={18} /></button></div>
        <div className="nav-caption">Monitoring</div>
        <nav className="nav-list">{navigation.map(({ to, label, Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-link ${isActive ? 'nav-link-active' : ''}`} onClick={() => setMobileOpen(false)}>
            <Icon size={17} aria-hidden="true" /><span>{label}</span>{label === 'Alerts & Notifications' && !loading && activeAlertCount > 0 && <span className="nav-count" aria-label={`${activeAlertCount} active alerts`}>{activeAlertCount}</span>}{label === 'Operations Overview' && <ChevronRight className="nav-chevron" size={14} />}
          </NavLink>
        ))}</nav>
        <div className="sidebar-spacer" />
        <div className="sidebar-status"><div className={`sidebar-status-title connection-${connectionState}`}><span className="signal-dot" /><span>Backend {connectionLabel}</span></div><p>Simulator <strong>{simulatorStatus?.running ? `Running · ${activeModeLabel}` : 'Stopped'}</strong></p>{events.length > 0 && <SimulatedBadge />}</div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <button className="mobile-menu" aria-label="Open navigation" aria-expanded={mobileOpen} onClick={() => setMobileOpen(true)}><Menu size={20} /></button>
          <div className="breadcrumb"><span>PLANT 01</span><span className="breadcrumb-divider">/</span><strong>TELEMETRY OVERVIEW</strong></div>
          <div className="topbar-status">
            {events.length > 0 && <SimulatedBadge />}
            <span className={`backend-pill connection-${connectionState}`} role="status"><span className="backend-dot" />Backend: {connectionLabel}</span>
            {isStale && <span className="stale-pill">Stale data</span>}
            {simulatorStatus?.running ? <>
              <span className="simulator-mode-label" role="status">{activeModeLabel} · {simulatorStatus.machine_count} machines · {simulatorStatus.interval_seconds ?? '—'}s</span>
              <button className="button button-small simulator-button" onClick={() => void stopSimulator()} disabled={simulatorBusy} aria-label="Stop simulator">
                <Square size={13} />Stop Simulation
              </button>
            </> : <div className="simulator-controls" aria-label="Simulator controls">
              <label className="sr-only" htmlFor="simulation-mode">Simulation mode</label>
              <select id="simulation-mode" className="simulator-select" value={selectedMode} onChange={(event) => {
                const nextMode = event.target.value as SimulationMode;
                setSelectedMode(nextMode);
                if (nextMode === 'mixed' && machineCount < 2) setMachineCount(3);
              }} disabled={simulatorBusy}>
                <option value="normal">Normal</option><option value="mixed">Mixed</option><option value="fault_scenario">Fault scenario</option>
              </select>
              <label className="sr-only" htmlFor="machine-count">Number of simulated machines</label>
              <input id="machine-count" className="simulator-count" type="number" min={selectedMode === 'mixed' ? 2 : 1} max={100} step={1} value={machineCount}
                onChange={(event) => setMachineCount(Math.max(selectedMode === 'mixed' ? 2 : 1, Math.min(100, Number.parseInt(event.target.value, 10) || 1)))} disabled={simulatorBusy} />
              <button className="button button-small simulator-button" onClick={() => void startSimulator(selectedMode, machineCount)} disabled={simulatorBusy} aria-label={startLabel}>
                <Play size={13} />{startLabel}
              </button>
            </div>}
          </div>
        </header>
        <main id="main-content" className="page-content"><Outlet /></main>
        {(error || simulatorError) && <div className="global-data-warning" role="status">{error || simulatorError}</div>}
        <footer className="app-footer"><span>INDUSTRIAL MACHINE FAILURE FORECASTING</span><span>Classification is an estimate from operating measurements.</span></footer>
      </div>
    </div>
  );
}
