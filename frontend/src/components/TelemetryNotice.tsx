import { AlertTriangle, Info, Radio } from 'lucide-react';
import { useTelemetry } from '../hooks/useTelemetry';
import { formatAge } from '../utils/telemetry';

const connectionLabels = {
  connected: 'Connected',
  reconnecting: 'Reconnecting',
  disconnected: 'Disconnected',
} as const;

export function TelemetryNotices() {
  const { events, connectionState, isStale, lastSuccessfulUpdateAt, now, staleAfterMs, simulatorStatus } = useTelemetry();
  const hasSyntheticEvents = events.length > 0 || simulatorStatus?.running === true;
  return <>
    <div className={`notice notice-neutral notice-connection notice-${connectionState}`} role="status">
      <Radio aria-hidden="true" size={17} />
      <span>Backend <strong>{connectionLabels[connectionState]}</strong>
        {lastSuccessfulUpdateAt === null ? ' · No successful update yet' : ` · Last successful update ${formatAge(new Date(lastSuccessfulUpdateAt).toISOString(), now)}`}
        {` · stale after ${Math.round(staleAfterMs / 1000)} sec`}
      </span>
    </div>
    {hasSyntheticEvents && <div className="notice notice-preview"><Info aria-hidden="true" size={17} /><span><strong>SIMULATED DATA</strong> — Backend simulator readings are synthetic and are not physical machine telemetry.</span></div>}
    {isStale && <div className="notice notice-warning" role="alert"><AlertTriangle aria-hidden="true" size={17} /><span><strong>Backend data is stale</strong> — No new valid telemetry arrived within the configured {Math.round(staleAfterMs / 1000)}-second threshold.</span></div>}
    {simulatorStatus?.error && <div className="notice notice-warning" role="alert"><AlertTriangle aria-hidden="true" size={17} /><span><strong>Simulator stopped with an error</strong> — {simulatorStatus.error}</span></div>}
  </>;
}

export function StaleNotice({ age }: { age: string }) {
  return <div className="notice notice-warning"><AlertTriangle aria-hidden="true" size={17} /><span><strong>Machine reading is stale</strong> — latest event is {age}. Its last known model prediction is shown as historical information.</span></div>;
}
