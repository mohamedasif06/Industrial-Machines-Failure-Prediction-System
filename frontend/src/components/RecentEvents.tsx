import { ArrowUpRight, Clock3 } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { TelemetryEvent } from '../types/telemetry';
import { formatAge } from '../utils/telemetry';
import { PredictionBadge } from './StatusBadge';

export function RecentEvents({ events, now, limit = 5 }: { events: TelemetryEvent[]; now: number; limit?: number }) {
  const recent = [...events].sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp)).slice(0, limit);
  if (recent.length === 0) return <p className="subtle-empty">No prediction events are available.</p>;
  return <ul className="event-list">{recent.map((event, index) => (
    <li className="event-row" key={`${event.machine_id}-${event.timestamp}-${index}`}>
      <div className="event-machine"><span className="event-machine-icon"><Clock3 size={14} /></span><div><strong>{event.machine_id}</strong><span>{formatAge(event.timestamp, now)} · Type {event.Type}</span></div></div>
      <div className="event-result"><PredictionBadge predictedClass={event.predicted_class} />{event.estimated_failure_probability !== undefined && <span className="mono probability">{(event.estimated_failure_probability * 100).toFixed(1)}%</span>}<Link className="icon-link" to={`/analysis?machine=${encodeURIComponent(event.machine_id)}`} aria-label={`Analyze event from ${event.machine_id}`}><ArrowUpRight size={15} /></Link></div>
    </li>
  ))}</ul>;
}
