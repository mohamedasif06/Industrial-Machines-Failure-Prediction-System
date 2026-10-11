import type { MachineHealth, MachineSummary, TelemetryEvent } from '../types/telemetry';
import { STALE_AFTER_MS } from '../services/backendTelemetry';

export { STALE_AFTER_MS };

export function getEventTime(event: TelemetryEvent): number {
  return Date.parse(event.timestamp);
}

export function latestEventPerMachine(events: TelemetryEvent[]): TelemetryEvent[] {
  const latest = new Map<string, TelemetryEvent>();
  for (const event of events) {
    const current = latest.get(event.machine_id);
    if (!current || getEventTime(event) > getEventTime(current)) latest.set(event.machine_id, event);
  }
  return [...latest.values()].sort((a, b) => a.machine_id.localeCompare(b.machine_id));
}

export function getMachineHealth(event: TelemetryEvent | null, now = Date.now()): MachineHealth {
  if (!event) return 'no-data';
  if (now - getEventTime(event) > STALE_AFTER_MS) return 'stale';
  return event.predicted_class === 1 ? 'attention' : 'normal';
}

export function summarizeMachines(events: TelemetryEvent[], now = Date.now(), machineIds?: string[]): MachineSummary[] {
  const latest = latestEventPerMachine(events);
  const byMachine = new Map(latest.map((event) => [event.machine_id, event]));
  const ids = machineIds ?? latest.map((event) => event.machine_id);
  return ids.map((machineId) => {
    const event = byMachine.get(machineId) ?? null;
    return {
      machineId,
      latestEvent: event,
      health: getMachineHealth(event, now),
      lastUpdatedMs: event ? getEventTime(event) : null,
    };
  });
}

export function formatTimestamp(timestamp: string): string {
  const time = new Date(timestamp);
  if (Number.isNaN(time.getTime())) return 'Invalid timestamp';
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium' }).format(time);
}

export function formatAge(timestamp: string, now = Date.now()): string {
  const elapsed = Math.max(0, now - Date.parse(timestamp));
  if (!Number.isFinite(elapsed)) return 'Unknown age';
  if (elapsed < 60_000) return `${Math.floor(elapsed / 1000)} sec ago`;
  if (elapsed < 3_600_000) return `${Math.floor(elapsed / 60_000)} min ago`;
  if (elapsed < 86_400_000) return `${Math.floor(elapsed / 3_600_000)} hr ago`;
  return `${Math.floor(elapsed / 86_400_000)} days ago`;
}

export function getSensorRows(event: TelemetryEvent) {
  return [
    { label: 'Type', value: event.Type, unit: 'variant' },
    { label: 'Air temperature', value: event['Air temperature [K]'], unit: 'K' },
    { label: 'Process temperature', value: event['Process temperature [K]'], unit: 'K' },
    { label: 'Rotational speed', value: event['Rotational speed [rpm]'], unit: 'rpm' },
    { label: 'Torque', value: event['Torque [Nm]'], unit: 'Nm' },
    { label: 'Tool wear', value: event['Tool wear [min]'], unit: 'min' },
  ];
}
