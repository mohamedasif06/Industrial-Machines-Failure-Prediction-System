import { useMemo, useState } from 'react';
import { AlertTriangle, BellRing, CircleCheck } from 'lucide-react';
import { DataStateView } from '../components/DataStateView';
import { PageHeader } from '../components/PageHeader';
import { Panel } from '../components/Panel';
import { TelemetryNotices } from '../components/TelemetryNotice';
import { useTelemetry } from '../hooks/useTelemetry';
import type { ManagedAlert } from '../services/backendTelemetry';
import { formatTimestamp } from '../utils/telemetry';

type AlertStatusFilter = 'all' | 'active' | 'resolved';
type AlertModeFilter = 'all' | 'normal' | 'fault_scenario';

export function AlertsNotifications() {
  const {
    alerts,
    machineIds,
    activeAlertCount,
    resolvedAlertCount,
    alertActivationThreshold,
    alertRecoveryThreshold,
  } = useTelemetry();
  const [machineFilter, setMachineFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState<AlertStatusFilter>('all');
  const [modeFilter, setModeFilter] = useState<AlertModeFilter>('all');
  const visibleAlerts = useMemo(() => [...alerts]
    .filter((alert) => machineFilter === 'all' || alert.machine_id === machineFilter)
    .filter((alert) => statusFilter === 'all' || alert.status === statusFilter)
    .filter((alert) => modeFilter === 'all' || alert.simulation_mode === modeFilter)
    .sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at)),
  [alerts, machineFilter, statusFilter, modeFilter]);

  return <>
    <PageHeader eyebrow="Managed model alerts" title="Alerts & Notifications" description="One alert tracks an ongoing sequence of failure-associated model predictions for a machine. A model flag is not confirmation of a mechanical breakdown." />
    <TelemetryNotices />
    <DataStateView />
    <section className="metrics-grid metrics-grid-three" aria-label="Managed alert summary">
      <article className="metric-card"><div className="metric-icon metric-icon-amber"><BellRing size={18} /></div><p className="eyebrow">Active alerts</p><p className="metric-value">{activeAlertCount}</p><p className="metric-detail">Unresolved machine conditions requiring attention</p></article>
      <article className="metric-card"><div className="metric-icon metric-icon-blue"><CircleCheck size={18} /></div><p className="eyebrow">Resolved alerts</p><p className="metric-value">{resolvedAlertCount}</p><p className="metric-detail">Retained completed alert episodes</p></article>
      <article className="metric-card"><div className="metric-icon metric-icon-slate"><AlertTriangle size={18} /></div><p className="eyebrow">Confirmation policy</p><p className="metric-value metric-word">{alertActivationThreshold} class 1 readings</p><p className="metric-detail">Resolve after {alertRecoveryThreshold} consecutive class 0 readings. Confirmation reduces noise but can delay alert creation.</p></article>
    </section>

    <Panel title="Managed alert episodes" eyebrow={`${visibleAlerts.length} matching alerts`}>
      <div className="filter-row">
        <label>Machine<select className="field-select" value={machineFilter} onChange={(event) => setMachineFilter(event.target.value)}><option value="all">All machines</option>{machineIds.map((id) => <option key={id} value={id}>{id}</option>)}</select></label>
        <label>Status<select className="field-select" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as AlertStatusFilter)}><option value="all">All statuses</option><option value="active">Active</option><option value="resolved">Resolved</option></select></label>
        <label>Simulation mode<select className="field-select" value={modeFilter} onChange={(event) => setModeFilter(event.target.value as AlertModeFilter)}><option value="all">All modes</option><option value="normal">Normal</option><option value="fault_scenario">Fault scenario</option></select></label>
        <span className="filter-hint">Each card is one alert episode; repeated telemetry remains in event history.</span>
      </div>
      {visibleAlerts.length === 0 ? <div className="quiet-state"><CircleCheck size={18} /><span>{alerts.length === 0 ? 'No managed alerts. Alerts open after the configured consecutive class 1 confirmation.' : 'No alerts match these filters.'}</span></div> : <div className="alerts-list">{visibleAlerts.map((alert) => <ManagedAlertCard alert={alert} key={alert.alert_id} />)}</div>}
    </Panel>
  </>;
}

function ManagedAlertCard({ alert }: { alert: ManagedAlert }) {
  const latest = alert.latest_event;
  const statusClass = alert.status === 'active' ? 'badge-warning' : 'badge-neutral';
  return <article className="alert-card">
    <div className="alert-card-heading">
      <div><span className="eyebrow">{alert.machine_id} · {alert.simulation_mode.replace('_', ' ')}</span><h3>Failure-associated prediction episode</h3></div>
      <span className={`status-badge ${statusClass}`}>{alert.status === 'active' ? 'Active' : 'Resolved'}</span>
    </div>
    <div className="alert-card-meta">
      <span>First detected: {formatTimestamp(alert.first_seen)}</span>
      <span>Alert activated: {formatTimestamp(alert.created_at)}</span>
      <span>Most recent class 1: {formatTimestamp(alert.last_seen)}</span>
      {alert.resolved_at && <span>Resolved: {formatTimestamp(alert.resolved_at)}</span>}
      <strong>{alert.occurrence_count} associated class 1 readings</strong>
    </div>
    <div className="alert-card-meta">
      <span>Latest model result: class {latest.predicted_class}</span>
      <span>Type {latest.Type}</span>
      <span>Model: {latest.model_name}</span>
      {latest.estimated_failure_probability !== undefined && <strong className="mono">Estimated {(latest.estimated_failure_probability * 100).toFixed(1)}%</strong>}
    </div>
    <div className="alert-readings"><span>Air {latest['Air temperature [K]'].toFixed(1)} K</span><span>Process {latest['Process temperature [K]'].toFixed(1)} K</span><span>Speed {latest['Rotational speed [rpm]']} rpm</span><span>Torque {latest['Torque [Nm]'].toFixed(1)} Nm</span><span>Wear {latest['Tool wear [min]'].toFixed(1)} min</span></div>
    <p>{alert.status === 'active' ? 'Active model-level flag. The system waits for consecutive class 0 readings before resolving it.' : 'Resolved after the configured recovery sequence of class 0 predictions.'} These synthetic predictions do not confirm a physical failure or its cause.</p>
  </article>;
}
