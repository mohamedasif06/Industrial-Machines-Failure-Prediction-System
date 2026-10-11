export const INPUT_FEATURES = [
  'Type',
  'Air temperature [K]',
  'Process temperature [K]',
  'Rotational speed [rpm]',
  'Torque [Nm]',
  'Tool wear [min]',
] as const;

export type FeatureName = (typeof INPUT_FEATURES)[number];
export type MachineType = 'L' | 'M' | 'H';
export type EventSimulationMode = 'normal' | 'fault_scenario';
export type SimulationMode = EventSimulationMode | 'mixed';

export interface TelemetryEvent {
  timestamp: string;
  session_id: string;
  machine_id: string;
  simulation_mode: EventSimulationMode;
  simulated: true;
  Type: MachineType;
  'Air temperature [K]': number;
  'Process temperature [K]': number;
  'Rotational speed [rpm]': number;
  'Torque [Nm]': number;
  'Tool wear [min]': number;
  predicted_class: 0 | 1;
  predicted_label?: string;
  model_name: string;
  estimated_failure_probability?: number;
}

export type MachineHealth = 'normal' | 'attention' | 'no-data' | 'stale';

export interface MachineSummary {
  machineId: string;
  latestEvent: TelemetryEvent | null;
  health: MachineHealth;
  lastUpdatedMs: number | null;
}

export type BackendConnectionState = 'connected' | 'reconnecting' | 'disconnected';
