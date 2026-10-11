import { INPUT_FEATURES, type EventSimulationMode, type SimulationMode, type TelemetryEvent } from '../types/telemetry';

const TYPES = ['L', 'M', 'H'] as const;
const EVENT_MODES: readonly EventSimulationMode[] = ['normal', 'fault_scenario'];
const SIMULATOR_MODES: readonly SimulationMode[] = ['normal', 'fault_scenario', 'mixed'];
const excludedKeys = ['UDI', 'Product ID', 'TWF', 'HDF', 'PWF', 'OSF', 'RNF'];
const numericFeatures = INPUT_FEATURES.slice(1);

const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim();
export const API_BASE_URL = (configuredBase || 'http://127.0.0.1:8000').replace(/\/+$/, '');

const configuredStaleThreshold = Number(import.meta.env.VITE_STALE_AFTER_MS);
export const STALE_AFTER_MS = Number.isFinite(configuredStaleThreshold) && configuredStaleThreshold > 0
  ? configuredStaleThreshold
  : 60_000;

export function isTelemetryStale(lastUpdateAt: number | null, now: number, thresholdMs = STALE_AFTER_MS): boolean {
  return lastUpdateAt !== null && now - lastUpdateAt > thresholdMs;
}

export interface MachineEndpointResponse {
  machine_count: number;
  session_id: string | null;
  machines_with_readings: number;
  machines: { machine_id: string; latest_event: unknown | null }[];
}

export interface EventEndpointResponse {
  event_count: number;
  events: unknown[];
}

export interface SimulatorStatus {
  running: boolean;
  mode: SimulationMode | null;
  machine_count: number;
  session_id: string | null;
  machine_ids: string[];
  active_machine_count: number;
  session_event_count: number;
  historical_machine_count: number;
  interval_seconds: number | null;
  error: string | null;
}

export interface ManagedAlert {
  alert_id: string;
  session_id: string;
  machine_id: string;
  condition: 'failure_associated_prediction';
  simulation_mode: EventSimulationMode;
  first_seen: string;
  created_at: string;
  last_seen: string;
  updated_at: string;
  occurrence_count: number;
  status: 'active' | 'resolved';
  resolved_at: string | null;
  latest_event: TelemetryEvent;
}

export interface AlertSnapshot {
  active_count: number;
  resolved_count: number;
  activation_threshold: number;
  recovery_threshold: number;
  alerts: ManagedAlert[];
}

export interface AlertWebSocketMessage {
  event_type: 'alert.created' | 'alert.updated' | 'alert.resolved';
  alert: ManagedAlert;
}

export interface BackendSnapshot {
  events: TelemetryEvent[];
  rejectedCount: number;
  simulatorStatus: SimulatorStatus;
  alertSnapshot: AlertSnapshot;
}

export function getWebSocketUrl(): string {
  const url = new URL('/ws/telemetry', API_BASE_URL);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

export function validateTelemetryEvent(value: unknown): value is TelemetryEvent {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const event = value as Record<string, unknown>;
  if (excludedKeys.some((key) => key in event)) return false;
  if (typeof event.timestamp !== 'string' || Number.isNaN(Date.parse(event.timestamp))) return false;
  if (typeof event.session_id !== 'string' || event.session_id.trim() === '') return false;
  if (typeof event.machine_id !== 'string' || event.machine_id.trim() === '') return false;
  if (event.simulated !== true || !EVENT_MODES.includes(event.simulation_mode as EventSimulationMode)) return false;
  if (!TYPES.includes(event.Type as (typeof TYPES)[number]) || ![0, 1].includes(event.predicted_class as number)) return false;
  if (typeof event.model_name !== 'string' || event.model_name.trim() === '') return false;
  for (const feature of numericFeatures) {
    if (typeof event[feature] !== 'number' || !Number.isFinite(event[feature])) return false;
  }
  const air = event['Air temperature [K]'] as number;
  const process = event['Process temperature [K]'] as number;
  const speed = event['Rotational speed [rpm]'] as number;
  const torque = event['Torque [Nm]'] as number;
  const wear = event['Tool wear [min]'] as number;
  if (air < 295.3 || air > 304.5 || process < 305.7 || process > 313.8 ||
      speed < 1168 || speed > 2886 || torque < 3.8 || torque > 76.6 || wear < 0 || wear > 253) return false;
  const probability = event.estimated_failure_probability;
  if (probability !== undefined && (typeof probability !== 'number' || !Number.isFinite(probability) || probability < 0 || probability > 1)) return false;
  return true;
}

export function validateManagedAlert(value: unknown): value is ManagedAlert {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const alert = value as Record<string, unknown>;
  if (typeof alert.alert_id !== 'string' || alert.alert_id.trim() === '' ||
      typeof alert.session_id !== 'string' || alert.session_id.trim() === '' ||
      typeof alert.machine_id !== 'string' || alert.machine_id.trim() === '' ||
      alert.condition !== 'failure_associated_prediction' ||
      !EVENT_MODES.includes(alert.simulation_mode as EventSimulationMode) ||
      !['active', 'resolved'].includes(alert.status as string) ||
      !Number.isInteger(alert.occurrence_count) || (alert.occurrence_count as number) < 1) return false;
  for (const field of ['first_seen', 'created_at', 'last_seen', 'updated_at']) {
    if (typeof alert[field] !== 'string' || Number.isNaN(Date.parse(alert[field] as string))) return false;
  }
  if (alert.status === 'resolved') {
    if (typeof alert.resolved_at !== 'string' || Number.isNaN(Date.parse(alert.resolved_at))) return false;
  } else if (alert.resolved_at !== null) return false;
  return validateTelemetryEvent(alert.latest_event) && alert.latest_event.machine_id === alert.machine_id;
}

export function validateAlertWebSocketMessage(value: unknown): value is AlertWebSocketMessage {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const message = value as Record<string, unknown>;
  return ['alert.created', 'alert.updated', 'alert.resolved'].includes(message.event_type as string) &&
    validateManagedAlert(message.alert);
}

export function mergeTelemetryEvents(
  current: TelemetryEvent[],
  incoming: TelemetryEvent[],
  maxEvents = 500,
): { events: TelemetryEvent[]; addedCount: number } {
  const byIdentity = new Map(current.map((event) => [`${event.session_id}\u0000${event.machine_id}\u0000${event.timestamp}`, event]));
  let addedCount = 0;
  for (const event of incoming) {
    const identity = `${event.session_id}\u0000${event.machine_id}\u0000${event.timestamp}`;
    if (!byIdentity.has(identity)) {
      byIdentity.set(identity, event);
      addedCount += 1;
    }
  }
  const events = [...byIdentity.values()]
    .sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp))
    .slice(-maxEvents);
  return { events, addedCount };
}

export function mergeManagedAlerts(current: ManagedAlert[], incoming: ManagedAlert[]): ManagedAlert[] {
  const byId = new Map(current.map((alert) => [alert.alert_id, alert]));
  for (const alert of incoming) {
    const previous = byId.get(alert.alert_id);
    if (!previous || Date.parse(alert.updated_at) >= Date.parse(previous.updated_at)) byId.set(alert.alert_id, alert);
  }
  return [...byId.values()].sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at));
}

async function getJson<T>(path: string, signal?: AbortSignal, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    signal: signal ?? init.signal,
    headers: { Accept: 'application/json', ...init.headers },
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json() as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch { /* Keep the status code when an error body is not JSON. */ }
    throw new Error(`Backend request failed (${detail}).`);
  }
  return response.json() as Promise<T>;
}

export async function loadBackendSnapshot(signal?: AbortSignal): Promise<BackendSnapshot> {
  const [machinesResponse, eventsResponse, simulatorStatus, rawAlertSnapshot] = await Promise.all([
    getJson<MachineEndpointResponse>('/api/machines', signal),
    getJson<EventEndpointResponse>('/api/events?limit=500', signal),
    getJson<SimulatorStatus>('/api/simulator/status', signal),
    getJson<Omit<AlertSnapshot, 'alerts'> & { alerts: unknown[] }>('/api/alerts', signal),
  ]);
  if (!Array.isArray(machinesResponse.machines) || !Array.isArray(eventsResponse.events)) {
    throw new Error('Backend returned an unexpected telemetry response format.');
  }
  const events: TelemetryEvent[] = [];
  let rejectedCount = 0;
  for (const value of [
    ...machinesResponse.machines.map((machine) => machine.latest_event).filter((event) => event !== null),
    ...eventsResponse.events,
  ]) {
    if (validateTelemetryEvent(value)) events.push(value);
    else rejectedCount += 1;
  }
  if (typeof simulatorStatus.running !== 'boolean' ||
      !Number.isInteger(simulatorStatus.machine_count) || simulatorStatus.machine_count < 0 ||
      !Array.isArray(simulatorStatus.machine_ids) ||
      (simulatorStatus.session_id !== null && typeof simulatorStatus.session_id !== 'string') ||
      (simulatorStatus.interval_seconds !== null &&
        (typeof simulatorStatus.interval_seconds !== 'number' || !Number.isFinite(simulatorStatus.interval_seconds) || simulatorStatus.interval_seconds <= 0)) ||
      (simulatorStatus.mode !== null && !SIMULATOR_MODES.includes(simulatorStatus.mode))) {
    throw new Error('Backend returned an unexpected simulator status format.');
  }
  if (!Array.isArray(rawAlertSnapshot.alerts) ||
      !Number.isInteger(rawAlertSnapshot.activation_threshold) || rawAlertSnapshot.activation_threshold < 1 ||
      !Number.isInteger(rawAlertSnapshot.recovery_threshold) || rawAlertSnapshot.recovery_threshold < 1) {
    throw new Error('Backend returned an unexpected managed-alert response format.');
  }
  if (!rawAlertSnapshot.alerts.every(validateManagedAlert)) {
    throw new Error('Backend returned an invalid managed-alert record.');
  }
  const alerts = mergeManagedAlerts([], rawAlertSnapshot.alerts);
  const activeCount = alerts.filter((alert) => alert.status === 'active' &&
    (simulatorStatus.session_id === null || alert.session_id === simulatorStatus.session_id)).length;
  const resolvedCount = alerts.filter((alert) => alert.status === 'resolved').length;
  if (rawAlertSnapshot.active_count !== activeCount || rawAlertSnapshot.resolved_count !== resolvedCount) {
    throw new Error('Backend managed-alert counts do not match the alert snapshot.');
  }
  const alertSnapshot = { ...rawAlertSnapshot, alerts };
  return { events: mergeTelemetryEvents([], events).events, rejectedCount, simulatorStatus, alertSnapshot };
}

export async function fetchSimulatorStatus(signal?: AbortSignal): Promise<SimulatorStatus> {
  return getJson<SimulatorStatus>('/api/simulator/status', signal);
}

export async function startBackendSimulator(mode: SimulationMode, machineCount = 3): Promise<SimulatorStatus> {
  return getJson<SimulatorStatus>('/api/simulator/start', undefined, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode, machine_count: machineCount }),
  });
}

export async function stopBackendSimulator(): Promise<SimulatorStatus> {
  return getJson<SimulatorStatus>('/api/simulator/stop', undefined, { method: 'POST' });
}
