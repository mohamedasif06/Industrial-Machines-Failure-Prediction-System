import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DataStateView } from '../components/DataStateView';
import { HealthBadge, PredictionBadge } from '../components/StatusBadge';
import { PageHeader } from '../components/PageHeader';
import { Panel } from '../components/Panel';
import { SensorTrendChart } from '../components/SensorTrendChart';
import { StaleNotice, TelemetryNotices } from '../components/TelemetryNotice';
import { useTelemetry } from '../hooks/useTelemetry';
import type { TelemetryEvent } from '../types/telemetry';
import { formatAge, formatTimestamp, getMachineHealth, getSensorRows } from '../utils/telemetry';

const sortLatestFirst = (events: TelemetryEvent[]) => [...events].sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));

export function LiveMachineMonitoring() {
  const { events, machineIds, now } = useTelemetry();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = machineIds.includes(searchParams.get('machine') ?? '') ? searchParams.get('machine')! : machineIds[0] ?? '';
  const machineEvents = useMemo(() => sortLatestFirst(events.filter((event) => event.machine_id === selectedId)), [events, selectedId]);
  const latest = machineEvents[0] ?? null;
  const health = getMachineHealth(latest, now);
  const sensorRows = latest ? getSensorRows(latest) : [];

  return <>
    <PageHeader eyebrow="Monitoring / machine detail" title="Live Machine Monitoring" description="Inspect recorded synthetic readings and the latest model result for a selected machine." action={<label className="select-label">Machine<select aria-label="Select machine" className="field-select" disabled={machineIds.length === 0} value={selectedId} onChange={(event) => setSearchParams({ machine: event.target.value })}>{machineIds.length === 0 ? <option value="">No machines</option> : machineIds.map((id) => <option key={id} value={id}>{id}</option>)}</select></label>} />
    <TelemetryNotices />
    <DataStateView />

    {!latest ? <Panel title="No machine reading" eyebrow="Machine detail"><p className="empty-copy">No valid reading is available for this machine from the backend.</p></Panel> : <>
      {health === 'stale' && <StaleNotice age={formatAge(latest.timestamp, now)} />}
      <Panel title={latest.machine_id} eyebrow={`Selected machine · Type ${latest.Type}`} action={health === 'stale' ? <HealthBadge health="stale" /> : <PredictionBadge predictedClass={latest.predicted_class} />}>
        <div className="prediction-summary"><div><span className="eyebrow">Latest model result</span><h2>{latest.predicted_class === 1 ? 'Attention required' : 'Normal prediction'}</h2><p>Class {latest.predicted_class} from the latest recorded input measurements.</p></div><div className="probability-block"><span>Estimated failure probability</span><strong>{latest.estimated_failure_probability === undefined ? 'Not available' : `${(latest.estimated_failure_probability * 100).toFixed(1)}%`}</strong><small>Model estimate · not a real-world guarantee</small></div></div>
        <div className="reading-meta"><span>Last event: {formatTimestamp(latest.timestamp)}</span><span>Mode: {latest.simulation_mode.replace('_', ' ')}</span><span>Model: {latest.model_name}</span></div>
      </Panel>

      <section className="sensor-grid" aria-label="Six model input measurements">{sensorRows.map(({ label, value, unit }) => (
        <article className="sensor-card" key={label}><span className="eyebrow">{label}</span><strong className="sensor-value">{value}<small>{unit}</small></strong><span className="sensor-source">Agreed model input</span></article>
      ))}</section>

      <SensorTrendChart events={machineEvents} dataKeys={['Air temperature [K]', 'Process temperature [K]']} title="Temperature readings over time" />
      <Panel title="Reading history" eyebrow={`${machineEvents.length} recorded events for this machine`}>
        {machineEvents.length < 2 ? <p className="empty-copy">More recorded readings are needed to compare changes over time.</p> : <div className="compact-event-list">{machineEvents.map((event) => <div className="compact-event" key={event.timestamp}><span className="mono">{formatTimestamp(event.timestamp)}</span><span>Air {event['Air temperature [K]'].toFixed(1)} K</span><span>Process {event['Process temperature [K]'].toFixed(1)} K</span><PredictionBadge predictedClass={event.predicted_class} /></div>)}</div>}
      </Panel>
    </>}
  </>;
}
