import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  fetchSimulatorStatus,
  loadBackendSnapshot,
  mergeTelemetryEvents,
  mergeManagedAlerts,
  startBackendSimulator,
  STALE_AFTER_MS,
  stopBackendSimulator,
  validateTelemetryEvent,
  validateAlertWebSocketMessage,
  getWebSocketUrl,
  isTelemetryStale,
  type SimulatorStatus,
} from '../services/backendTelemetry';
import { TelemetryContext, type TelemetryContextValue } from '../services/telemetryContext';
import type { BackendConnectionState, SimulationMode, TelemetryEvent } from '../types/telemetry';
import type { ManagedAlert } from '../services/backendTelemetry';

const RECENT_EVENT_LIMIT = 500;

export function TelemetryProvider({ children }: { children: ReactNode }) {
  const [events, setEvents] = useState<TelemetryEvent[]>([]);
  const [alerts, setAlerts] = useState<ManagedAlert[]>([]);
  const [alertActivationThreshold, setAlertActivationThreshold] = useState(2);
  const [alertRecoveryThreshold, setAlertRecoveryThreshold] = useState(3);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rejectedCount, setRejectedCount] = useState(0);
  const [request, setRequest] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [connectionState, setConnectionState] = useState<BackendConnectionState>('disconnected');
  const [lastSuccessfulUpdateAt, setLastSuccessfulUpdateAt] = useState<number | null>(null);
  const [simulatorStatus, setSimulatorStatus] = useState<SimulatorStatus | null>(null);
  const [simulatorBusy, setSimulatorBusy] = useState(false);
  const [simulatorError, setSimulatorError] = useState<string | null>(null);
  const seenEventKeys = useRef(new Set<string>());
  const alertUpdateRevision = useRef(0);
  const alertUpdatesSinceSnapshot = useRef<Array<{ revision: number; alert: ManagedAlert }>>([]);
  const currentSessionRef = useRef<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let alive = true;
    let socket: WebSocket | null = null;
    let reconnectTimer = 0;
    let statusTimer = 0;
    let hasConnected = false;
    let reconnectAttempt = 0;

    setLoading(true);
    setError(null);
    setConnectionState('disconnected');

    function refreshSnapshot(showLoading: boolean) {
      const snapshotRevision = alertUpdateRevision.current;
      if (showLoading) setLoading(true);
      loadBackendSnapshot(controller.signal)
        .then((snapshot) => {
          if (!alive) return;
          for (const event of snapshot.events) remember(`${event.session_id}\u0000${event.machine_id}\u0000${event.timestamp}`);
          setEvents((current) => mergeTelemetryEvents(current, snapshot.events, RECENT_EVENT_LIMIT).events);
          const newerSocketAlerts = alertUpdatesSinceSnapshot.current
            .filter((entry) => entry.revision > snapshotRevision)
            .map((entry) => entry.alert);
          setAlerts(mergeManagedAlerts(snapshot.alertSnapshot.alerts, newerSocketAlerts));
          alertUpdatesSinceSnapshot.current = alertUpdatesSinceSnapshot.current
            .filter((entry) => entry.revision > snapshotRevision);
          setAlertActivationThreshold(snapshot.alertSnapshot.activation_threshold);
          setAlertRecoveryThreshold(snapshot.alertSnapshot.recovery_threshold);
          setRejectedCount((count) => count + snapshot.rejectedCount);
          setSimulatorStatus(snapshot.simulatorStatus);
          currentSessionRef.current = snapshot.simulatorStatus.session_id;
          setLastSuccessfulUpdateAt(Date.now());
          setError(null);
        })
        .catch((reason: unknown) => {
          if (alive && !controller.signal.aborted) {
            setError(reason instanceof Error ? reason.message : 'Could not load telemetry from the backend.');
          }
        })
        .finally(() => {
          if (showLoading && alive && !controller.signal.aborted) setLoading(false);
        });
    }

    const connectSocket = () => {
      if (!alive) return;
      let activeSocket: WebSocket;
      try {
        activeSocket = new WebSocket(getWebSocketUrl());
        socket = activeSocket;
      } catch {
        setConnectionState(hasConnected ? 'reconnecting' : 'disconnected');
        scheduleReconnect();
        return;
      }

      activeSocket.onopen = () => {
        if (!alive) return;
        const isReconnect = hasConnected;
        hasConnected = true;
        reconnectAttempt = 0;
        setConnectionState('connected');
        if (isReconnect) refreshSnapshot(false);
      };
      activeSocket.onmessage = (message) => {
        if (!alive) return;
        try {
          const parsed: unknown = JSON.parse(String(message.data));
          if (typeof parsed === 'object' && parsed !== null && 'event_type' in parsed) {
            if (parsed.event_type === 'session.snapshot') {
              fetchSimulatorStatus(controller.signal).then((status) => {
                if (!alive) return;
                const sessionChanged = currentSessionRef.current !== status.session_id;
                setSimulatorStatus(status);
                currentSessionRef.current = status.session_id;
                if (sessionChanged) refreshSnapshot(false);
              }).catch(() => { /* The next status poll or REST snapshot can recover this update. */ });
              return;
            }
            if (!validateAlertWebSocketMessage(parsed)) {
              setRejectedCount((count) => count + 1);
              return;
            }
            alertUpdateRevision.current += 1;
            if (currentSessionRef.current && parsed.alert.session_id !== currentSessionRef.current) return;
            alertUpdatesSinceSnapshot.current.push({ revision: alertUpdateRevision.current, alert: parsed.alert });
            if (alertUpdatesSinceSnapshot.current.length > RECENT_EVENT_LIMIT) alertUpdatesSinceSnapshot.current.shift();
            setAlerts((current) => mergeManagedAlerts(current, [parsed.alert]));
            setLastSuccessfulUpdateAt(Date.now());
            setError(null);
            return;
          }
          if (!validateTelemetryEvent(parsed)) {
            setRejectedCount((count) => count + 1);
            return;
          }
          if (currentSessionRef.current && parsed.session_id !== currentSessionRef.current) return;
          const identity = `${parsed.session_id}\u0000${parsed.machine_id}\u0000${parsed.timestamp}`;
          if (!seenEventKeys.current.has(identity)) {
            remember(identity);
            setEvents((current) => mergeTelemetryEvents(current, [parsed], RECENT_EVENT_LIMIT).events);
            setLastSuccessfulUpdateAt(Date.now());
            setError(null);
          }
        } catch {
          setRejectedCount((count) => count + 1);
        }
      };
      activeSocket.onerror = () => {
        // Browsers report connection failure through onclose; close explicitly
        // so the single reconnect path below handles all failure cases.
        activeSocket.close();
      };
      activeSocket.onclose = () => {
        if (!alive) return;
        setConnectionState(hasConnected ? 'reconnecting' : 'disconnected');
        scheduleReconnect();
      };
    };

    const remember = (identity: string) => {
      seenEventKeys.current.add(identity);
      if (seenEventKeys.current.size > RECENT_EVENT_LIMIT * 2) {
        const oldest = seenEventKeys.current.values().next().value as string | undefined;
        if (oldest) seenEventKeys.current.delete(oldest);
      }
    };

    function scheduleReconnect() {
      if (!alive) return;
      const delay = Math.min(500 * 2 ** reconnectAttempt, 10_000);
      reconnectAttempt += 1;
      window.clearTimeout(reconnectTimer);
      reconnectTimer = window.setTimeout(connectSocket, delay);
    }

    // Establish the WebSocket before loading the REST snapshot. Any event that
    // arrives during the requests is merged by machine/timestamp identity.
    connectSocket();
    refreshSnapshot(true);

    const refreshSimulatorStatus = () => {
      fetchSimulatorStatus(controller.signal)
        .then((status) => {
          if (!alive) return;
          const sessionChanged = currentSessionRef.current !== status.session_id;
          setSimulatorStatus(status);
          currentSessionRef.current = status.session_id;
          if (sessionChanged) refreshSnapshot(false);
        })
        .catch(() => { /* Telemetry and socket state provide the visible connection errors. */ });
    };
    statusTimer = window.setInterval(refreshSimulatorStatus, 5_000);

    return () => {
      alive = false;
      controller.abort();
      window.clearTimeout(reconnectTimer);
      window.clearInterval(statusTimer);
      socket?.close();
    };
  }, [request]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  const operateSimulator = useCallback(async (operation: 'start' | 'stop', mode?: SimulationMode, machineCount?: number) => {
    setSimulatorBusy(true);
    setSimulatorError(null);
    try {
      const status = operation === 'start'
        ? await startBackendSimulator(mode ?? 'normal', machineCount ?? 3)
        : await stopBackendSimulator();
      setSimulatorStatus(status);
      currentSessionRef.current = status.session_id;
    } catch (reason) {
      setSimulatorError(reason instanceof Error ? reason.message : 'Simulator request failed.');
    } finally {
      setSimulatorBusy(false);
    }
  }, []);

  const reload = useCallback(() => setRequest((current) => current + 1), []);
  const startSimulator = useCallback((mode: SimulationMode, machineCount: number) => operateSimulator('start', mode, machineCount), [operateSimulator]);
  const stopSimulator = useCallback(() => operateSimulator('stop'), [operateSimulator]);
  const currentSessionId = simulatorStatus?.session_id ?? null;
  const sessionEvents = useMemo(() => currentSessionId
    ? events.filter((event) => event.session_id === currentSessionId)
    : events, [events, currentSessionId]);
  const sessionAlerts = useMemo(() => currentSessionId
    ? alerts.filter((alert) => alert.session_id === currentSessionId)
    : alerts, [alerts, currentSessionId]);
  const machineIds = useMemo(() => simulatorStatus?.machine_ids?.length
    ? simulatorStatus.machine_ids
    : [...new Set(sessionEvents.map((event) => event.machine_id))].sort(), [simulatorStatus, sessionEvents]);
  const isStale = sessionEvents.length > 0 && isTelemetryStale(lastSuccessfulUpdateAt, now, STALE_AFTER_MS);
  const activeAlertCount = sessionAlerts.filter((alert) => alert.status === 'active').length;
  const resolvedAlertCount = sessionAlerts.filter((alert) => alert.status === 'resolved').length;

  const value = useMemo<TelemetryContextValue>(() => ({
    events: sessionEvents,
    machineIds,
    historicalMachineCount: simulatorStatus?.historical_machine_count ?? 0,
    sessionEventCount: Math.max(simulatorStatus?.session_event_count ?? 0, sessionEvents.length),
    alerts: sessionAlerts,
    activeAlertCount,
    resolvedAlertCount,
    alertActivationThreshold,
    alertRecoveryThreshold,
    loading,
    error,
    rejectedCount,
    now,
    connectionState,
    staleAfterMs: STALE_AFTER_MS,
    lastSuccessfulUpdateAt,
    isStale,
    simulatorStatus,
    simulatorBusy,
    simulatorError,
    reload,
    startSimulator,
    stopSimulator,
  }), [sessionEvents, machineIds, simulatorStatus, sessionAlerts, activeAlertCount, resolvedAlertCount, alertActivationThreshold, alertRecoveryThreshold, loading, error, rejectedCount, now, connectionState, lastSuccessfulUpdateAt, isStale,
    simulatorBusy, simulatorError, reload, startSimulator, stopSimulator]);

  return <TelemetryContext.Provider value={value}>{children}</TelemetryContext.Provider>;
}
