import { afterEach, describe, expect, it, vi } from 'vitest';
import { getWebSocketUrl, isTelemetryStale, loadBackendSnapshot, mergeManagedAlerts, mergeTelemetryEvents, validateAlertWebSocketMessage, validateManagedAlert, validateTelemetryEvent, type ManagedAlert } from '../src/services/backendTelemetry';
import { getMachineHealth, latestEventPerMachine, summarizeMachines } from '../src/utils/telemetry';
import { INPUT_FEATURES, type TelemetryEvent } from '../src/types/telemetry';

function event(machineId: string, timestamp: string, predictedClass: 0 | 1, sessionId = 'session-1'): TelemetryEvent {
  return {
    timestamp,
    session_id: sessionId,
    machine_id: machineId,
    simulation_mode: 'normal',
    simulated: true,
    Type: 'M',
    'Air temperature [K]': 300,
    'Process temperature [K]': 310,
    'Rotational speed [rpm]': 1500,
    'Torque [Nm]': 40,
    'Tool wear [min]': 100,
    predicted_class: predictedClass,
    model_name: 'XGBoost',
    estimated_failure_probability: 0.2,
  };
}

function alert(alertId: string, status: 'active' | 'resolved', updatedAt: string): ManagedAlert {
  return {
    alert_id: alertId,
    session_id: 'session-1',
    machine_id: 'SIM-01',
    condition: 'failure_associated_prediction',
    simulation_mode: 'fault_scenario',
    first_seen: '2026-10-10T10:00:00Z',
    created_at: '2026-10-10T10:00:05Z',
    last_seen: updatedAt,
    updated_at: updatedAt,
    occurrence_count: 4,
    status,
    resolved_at: status === 'resolved' ? updatedAt : null,
    latest_event: event('SIM-01', updatedAt, status === 'resolved' ? 0 : 1),
  };
}

afterEach(() => vi.unstubAllGlobals());

describe('backend telemetry contract and aggregation', () => {
  it('validates exact six agreed inputs and rejects excluded columns', () => {
    const reading = event('SIM-01', new Date().toISOString(), 0);
    expect(Object.keys(reading).filter((key) => INPUT_FEATURES.includes(key as (typeof INPUT_FEATURES)[number]))).toEqual(INPUT_FEATURES);
    expect(validateTelemetryEvent(reading)).toBe(true);
    expect(validateTelemetryEvent({ ...reading, UDI: 17 })).toBe(false);
    expect(validateTelemetryEvent({ ...reading, 'Torque [Nm]': 90 })).toBe(false);
    expect(validateTelemetryEvent({ ...reading, estimated_failure_probability: 1.4 })).toBe(false);
    expect(validateTelemetryEvent({ ...reading, simulated: false })).toBe(false);
  });

  it('loads latest machine states and recent history from the actual REST response shape', async () => {
    const latest = event('SIM-01', new Date().toISOString(), 1);
    const fetchStub = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ machine_count: 1, session_id: 'session-1', machines_with_readings: 1, machines: [{ machine_id: 'SIM-01', latest_event: latest }] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ event_count: 1, events: [latest] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ running: true, mode: 'normal', machine_count: 1, session_id: 'session-1', machine_ids: ['SIM-01'], active_machine_count: 1, session_event_count: 1, historical_machine_count: 0, interval_seconds: 2, error: null }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ active_count: 1, resolved_count: 0, activation_threshold: 2, recovery_threshold: 3, alerts: [alert('a-1', 'active', new Date().toISOString())] }) });
    vi.stubGlobal('fetch', fetchStub);
    const snapshot = await loadBackendSnapshot();
    expect(snapshot.events).toEqual([latest]);
    expect(snapshot.simulatorStatus.running).toBe(true);
    expect(snapshot.alertSnapshot.active_count).toBe(1);
    expect(snapshot.alertSnapshot.alerts).toHaveLength(1);
    expect(fetchStub.mock.calls.map(([url]) => url)).toEqual([
      'http://127.0.0.1:8000/api/machines',
      'http://127.0.0.1:8000/api/events?limit=500',
      'http://127.0.0.1:8000/api/simulator/status',
      'http://127.0.0.1:8000/api/alerts',
    ]);
  });

  it('deduplicates by machine and timestamp without increasing event counts', () => {
    const original = event('SIM-01', '2026-10-10T10:00:00Z', 0);
    const repeated = { ...original };
    const newer = event('SIM-01', '2026-10-10T10:01:00Z', 1);
    const merged = mergeTelemetryEvents([original], [repeated, newer]);
    expect(merged.addedCount).toBe(1);
    expect(merged.events).toHaveLength(2);
    expect(latestEventPerMachine(merged.events)[0].predicted_class).toBe(1);
    expect(summarizeMachines(merged.events)).toHaveLength(1);
  });

  it('keeps identical timestamps distinct across sessions and includes machines with no reading', () => {
    const timestamp = new Date().toISOString();
    const firstSession = event('SIM-01', timestamp, 0, 'session-1');
    const secondSession = event('SIM-01', timestamp, 1, 'session-2');
    const merged = mergeTelemetryEvents([], [firstSession, secondSession]);
    expect(merged.events).toHaveLength(2);
    expect(summarizeMachines([secondSession], Date.now(), ['SIM-01', 'SIM-02']).map((machine) => machine.health))
      .toEqual(['attention', 'no-data']);
  });

  it('validates alert episodes and merges repeated updates by episode identity', () => {
    const active = alert('SIM-01:failure_associated_prediction:1', 'active', '2026-10-10T10:00:05Z');
    const updated = { ...active, occurrence_count: 50, updated_at: '2026-10-10T10:05:00Z', last_seen: '2026-10-10T10:05:00Z' };
    const envelope = { event_type: 'alert.updated', alert: updated };
    expect(validateManagedAlert(active)).toBe(true);
    expect(validateAlertWebSocketMessage(envelope)).toBe(true);
    expect(validateManagedAlert({ ...active, latest_event: { ...active.latest_event, UDI: 1 } })).toBe(false);
    const merged = mergeManagedAlerts([active], [active, updated]);
    expect(merged).toHaveLength(1);
    expect(merged[0].occurrence_count).toBe(50);
    const resolved = alert('SIM-01:failure_associated_prediction:2', 'resolved', '2026-10-10T10:10:00Z');
    expect(mergeManagedAlerts(merged, [resolved])).toHaveLength(2);
  });

  it('distinguishes stale machine events and no-data states', () => {
    const recorded = event('SIM-01', '2026-10-10T10:00:00Z', 1);
    expect(getMachineHealth(recorded, Date.parse('2026-10-10T10:02:00Z'))).toBe('stale');
    expect(getMachineHealth(null)).toBe('no-data');
  });

  it('marks the connection data stale only after the configured interval without valid updates', () => {
    expect(isTelemetryStale(10_000, 69_999, 60_000)).toBe(false);
    expect(isTelemetryStale(10_000, 70_001, 60_000)).toBe(true);
    expect(isTelemetryStale(null, 70_001, 60_000)).toBe(false);
  });

  it('derives a WebSocket address from the configured backend URL', () => {
    expect(getWebSocketUrl()).toBe('ws://127.0.0.1:8000/ws/telemetry');
  });
});
