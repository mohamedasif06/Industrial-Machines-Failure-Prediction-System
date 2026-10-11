import { ArrowUpRight, Radio } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { MachineSummary } from '../types/telemetry';
import { formatAge } from '../utils/telemetry';
import { HealthBadge, PredictionBadge } from './StatusBadge';

export function MachineTable({ machines, now }: { machines: MachineSummary[]; now: number }) {
  if (machines.length === 0) return <div className="table-empty"><Radio size={20} /><span>No machine events are available from the backend.</span></div>;
  return (
    <div className="table-scroll">
      <table className="machine-table">
        <thead><tr><th>Machine</th><th>Latest readings</th><th>Latest prediction</th><th>Telemetry age</th><th><span className="sr-only">Details</span></th></tr></thead>
        <tbody>{machines.map(({ machineId, latestEvent, health }) => (
          <tr key={machineId}>
            <td><strong className="machine-id">{machineId}</strong>{latestEvent && <span className="table-subtext">Type {latestEvent.Type} · {latestEvent.simulation_mode.replace('_', ' ')}</span>}</td>
            <td>{latestEvent ? <div className="reading-summary"><span>{latestEvent['Air temperature [K]'].toFixed(1)} K air</span><span>{latestEvent['Torque [Nm]'].toFixed(1)} Nm torque</span><span>{latestEvent['Tool wear [min]'].toFixed(1)} min wear</span></div> : <span className="muted">No reading</span>}</td>
            <td>{latestEvent ? <div className="prediction-stack"><PredictionBadge predictedClass={latestEvent.predicted_class} />{health === 'stale' && <HealthBadge health="stale" />}</div> : <HealthBadge health="no-data" />}</td>
            <td>{latestEvent ? <span className={health === 'stale' ? 'text-warning mono' : 'muted mono'}>{formatAge(latestEvent.timestamp, now)}</span> : '—'}</td>
            <td><Link className="icon-link" to={`/monitoring?machine=${encodeURIComponent(machineId)}`} aria-label={`View details for ${machineId}`}><ArrowUpRight size={16} /></Link></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}
