import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DataStateView } from '../components/DataStateView';
import { PageHeader } from '../components/PageHeader';
import { Panel } from '../components/Panel';
import { PredictionBadge } from '../components/StatusBadge';
import { SensorTrendChart } from '../components/SensorTrendChart';
import { StaleNotice, TelemetryNotices } from '../components/TelemetryNotice';
import { useTelemetry } from '../hooks/useTelemetry';
import type { TelemetryEvent } from '../types/telemetry';
import { formatAge, formatTimestamp, getMachineHealth, getSensorRows } from '../utils/telemetry';

const newestFirst = (events: TelemetryEvent[]) => [...events].sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));

export function PredictionAnalysis() {
  const { events, machineIds, now } = useTelemetry();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = machineIds.includes(searchParams.get('machine') ?? '') ? searchParams.get('machine')! : machineIds[0] ?? '';
  const history = useMemo(() => newestFirst(events.filter((event) => event.machine_id === selectedId)), [events, selectedId]);
  const latest = history[0] ?? null;

  return <>
    <PageHeader eyebrow="Analysis / prediction review" title="Failure Prediction & Analysis" description="Review a model classification with the exact six measurements supplied for that event." action={<label className="select-label">Machine<select aria-label="Select analysis machine" className="field-select" disabled={machineIds.length === 0} value={selectedId} onChange={(event) => setSearchParams({ machine: event.target.value })}>{machineIds.length === 0 ? <option value="">No machines</option> : machineIds.map((id) => <option key={id} value={id}>{id}</option>)}</select></label>} />
    <TelemetryNotices />
    <DataStateView />
    {!latest ? <Panel title="No prediction history" eyebrow="Analysis"><p className="empty-copy">There is no valid prediction event in the backend event history.</p></Panel> : <>
      {getMachineHealth(latest, now) === 'stale' && <StaleNotice age={formatAge(latest.timestamp, now)} />}
      <div className="analysis-grid">
        <Panel title="Latest model prediction" eyebrow={`${latest.machine_id} · ${formatTimestamp(latest.timestamp)}`} className="prediction-feature-panel">
          <div className="prediction-feature-result"><PredictionBadge predictedClass={latest.predicted_class} /><strong>{latest.estimated_failure_probability === undefined ? 'Probability unavailable' : `${(latest.estimated_failure_probability * 100).toFixed(1)}%`}</strong><span>model-estimated probability</span></div>
          <p className="analysis-explanation">The model evaluates the six operating measurements and classifies whether this input resembles conditions associated with the failure class in its training data. This is a model output, not confirmation of a physical failure.</p>
          <div className="limitation-note"><strong>Interpretation limits</strong><ul><li>It does not guarantee a future breakdown.</li><li>It does not estimate an exact failure time.</li><li>The probability is not a guaranteed real-world likelihood.</li></ul></div>
        </Panel>
        <Panel title="Input measurements" eyebrow="Six agreed model features">
          <dl className="measurement-list">{getSensorRows(latest).map(({ label, value, unit }) => <div key={label}><dt>{label}</dt><dd>{value}<span>{unit}</span></dd></div>)}</dl>
          <div className="metadata-note"><span>Machine ID</span><strong>{latest.machine_id}</strong><span>Event time</span><strong>{formatTimestamp(latest.timestamp)}</strong><span>Simulation mode</span><strong>{latest.simulation_mode.replace('_', ' ')}</strong></div>
        </Panel>
      </div>
      <SensorTrendChart events={history} dataKeys={['Torque [Nm]', 'Tool wear [min]']} title="Recorded input measurements" />
      <Panel title="Prediction history" eyebrow={`${history.length} events · one row per recorded event`}>
        {history.length < 2 ? <p className="empty-copy">No comparison history is available yet.</p> : <div className="compact-event-list">{history.map((event) => <div className="compact-event" key={event.timestamp}><span className="mono">{formatTimestamp(event.timestamp)}</span><span>Torque {event['Torque [Nm]'].toFixed(1)} Nm</span><span>Wear {event['Tool wear [min]'].toFixed(1)} min</span><PredictionBadge predictedClass={event.predicted_class} /><strong className="mono">{event.estimated_failure_probability === undefined ? '—' : `${(event.estimated_failure_probability * 100).toFixed(1)}%`}</strong></div>)}</div>}
      </Panel>
    </>}
  </>;
}
