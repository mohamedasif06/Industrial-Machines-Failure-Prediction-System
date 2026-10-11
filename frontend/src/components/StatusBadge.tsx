import { AlertTriangle, CheckCircle2, CircleHelp, Clock3, Database, type LucideIcon } from 'lucide-react';
import type { MachineHealth } from '../types/telemetry';

const healthPresentation: Record<MachineHealth, { label: string; Icon: LucideIcon; className: string }> = {
  normal: { label: 'Normal prediction', Icon: CheckCircle2, className: 'badge-normal' },
  attention: { label: 'Attention required', Icon: AlertTriangle, className: 'badge-warning' },
  'no-data': { label: 'No recent data', Icon: CircleHelp, className: 'badge-neutral' },
  stale: { label: 'Data stale', Icon: Clock3, className: 'badge-warning' },
};

export function HealthBadge({ health }: { health: MachineHealth }) {
  const { label, Icon, className } = healthPresentation[health];
  return <span className={`status-badge ${className}`}><Icon aria-hidden="true" size={14} />{label}</span>;
}

export function SimulatedBadge() {
  return <span className="status-badge badge-simulated"><Database aria-hidden="true" size={13} />Simulated data</span>;
}

export function PredictionBadge({ predictedClass }: { predictedClass: 0 | 1 }) {
  const health = predictedClass === 1 ? 'attention' : 'normal';
  const { label, Icon, className } = healthPresentation[health];
  return <span className={`status-badge ${className}`}><Icon aria-hidden="true" size={14} />{label}</span>;
}
