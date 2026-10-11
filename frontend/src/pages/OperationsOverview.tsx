import { Activity, AlertTriangle, Boxes, Radio, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import { DataStateView } from '../components/DataStateView';
import { MachineTable } from '../components/MachineTable';
import { MetricCard } from '../components/MetricCard';
import { PageHeader } from '../components/PageHeader';
import { Panel } from '../components/Panel';
import { RecentEvents } from '../components/RecentEvents';
import { SensorTrendChart } from '../components/SensorTrendChart';
import { TelemetryNotices } from '../components/TelemetryNotice';
import { useTelemetry } from '../hooks/useTelemetry';
import { summarizeMachines } from '../utils/telemetry';

export function OperationsOverview() {
  const { events, machineIds, sessionEventCount, simulatorStatus, now, loading, lastSuccessfulUpdateAt, staleAfterMs } = useTelemetry();
  const machines = summarizeMachines(events, now, machineIds);
  const normal = machines.filter((machine) => machine.latestEvent?.predicted_class === 0).length;
  const attention = machines.filter((machine) => machine.latestEvent?.predicted_class === 1).length;
  const stale = machines.filter((machine) => machine.health === 'stale').length;
  return <>
    <PageHeader eyebrow="Operations / overview" title="Machine Health Overview" description="See each machine’s latest model prediction and how recent its recorded reading is." action={<span className="latest-update"><span className="live-dot" />{lastSuccessfulUpdateAt ? `Updated ${new Date(lastSuccessfulUpdateAt).toLocaleTimeString()}` : 'Waiting for backend update'}</span>} />
    <TelemetryNotices />
    <DataStateView />

    <section className="metrics-grid" aria-label="Fleet summary">
      <MetricCard label="Machines in Session" value={loading ? '—' : machines.length} detail={`${simulatorStatus?.active_machine_count ?? 0} currently active · selected session configuration`} Icon={Boxes} tone="blue" />
      <MetricCard label="Normal Predictions" value={loading ? '—' : normal} detail="Latest model class is 0" Icon={ShieldCheck} tone="green" />
      <MetricCard label="Attention Required" value={loading ? '—' : attention} detail="Latest model class is 1 · not a confirmed breakdown" Icon={AlertTriangle} tone="amber" />
      <MetricCard label="Stale Machine Data" value={loading ? '—' : stale} detail={`No valid machine event within ${Math.round(staleAfterMs / 1000)} seconds`} Icon={Activity} tone="slate" />
    </section>

    <Panel title="Machine status" eyebrow={`${machines.length} machines in selected session · ${sessionEventCount} events`} action={<Link className="text-link" to="/monitoring">Open monitoring <span aria-hidden="true">→</span></Link>}>
      <p className="panel-caption">Prediction counts use the latest valid event per current-session machine. Event totals count repeated readings; previous session machine IDs remain in retained history.</p>
      <MachineTable machines={machines} now={now} />
    </Panel>

    <div className="dashboard-lower-grid">
      <SensorTrendChart events={events} dataKeys={['Torque [Nm]']} title="Torque trend" />
      <Panel title="Recent prediction events" eyebrow="Event count, not machine count" action={<Link className="text-link" to="/analysis">View analysis <span aria-hidden="true">→</span></Link>}>
        <RecentEvents events={events} now={now} limit={5} />
      </Panel>
    </div>

    <Panel title="Flagged model events" eyebrow="Latest event per machine" action={<Link className="text-link" to="/alerts">Review events <span aria-hidden="true">→</span></Link>}>
      {attention === 0 ? <div className="quiet-state"><Radio size={18} /><span>No latest machine predictions are flagged in the backend event history.</span></div> : <RecentEvents events={machines.flatMap((machine) => machine.latestEvent?.predicted_class === 1 ? [machine.latestEvent] : [])} now={now} limit={4} />}
    </Panel>
  </>;
}
