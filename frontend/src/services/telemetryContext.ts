import { createContext } from 'react';
import type { BackendConnectionState, SimulationMode, TelemetryEvent } from '../types/telemetry';
import type { ManagedAlert, SimulatorStatus } from './backendTelemetry';

export interface TelemetryContextValue {
  events: TelemetryEvent[];
  machineIds: string[];
  historicalMachineCount: number;
  sessionEventCount: number;
  alerts: ManagedAlert[];
  activeAlertCount: number;
  resolvedAlertCount: number;
  alertActivationThreshold: number;
  alertRecoveryThreshold: number;
  loading: boolean;
  error: string | null;
  rejectedCount: number;
  now: number;
  connectionState: BackendConnectionState;
  staleAfterMs: number;
  lastSuccessfulUpdateAt: number | null;
  isStale: boolean;
  simulatorStatus: SimulatorStatus | null;
  simulatorBusy: boolean;
  simulatorError: string | null;
  reload: () => void;
  startSimulator: (mode: SimulationMode, machineCount: number) => Promise<void>;
  stopSimulator: () => Promise<void>;
}

export const TelemetryContext = createContext<TelemetryContextValue | null>(null);
