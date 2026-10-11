import { useMemo } from 'react';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { TelemetryEvent } from '../types/telemetry';
import { Panel } from './Panel';

const seriesColors: Record<string, string> = {
  'Air temperature [K]': '#38bdf8',
  'Process temperature [K]': '#f59e0b',
  'Torque [Nm]': '#f59e0b',
  'Rotational speed [rpm]': '#38bdf8',
  'Tool wear [min]': '#a2b2cb',
};

export function SensorTrendChart({ events, dataKeys, title, className = '' }: {
  events: TelemetryEvent[];
  dataKeys: string[];
  title: string;
  className?: string;
}) {
  const chartData = useMemo(() => [...events]
    .sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp))
    .map((event) => ({ ...event, chartTime: new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) })), [events]);

  return (
    <Panel title={title} eyebrow="Recorded preview readings" className={className}>
      {chartData.length < 2 ? (
        <div className="chart-empty">At least two readings are needed to show a trend.</div>
      ) : (
        <div className="chart-wrap" role="img" aria-label={`${title} from ${chartData.length} recorded simulated readings`}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
              <CartesianGrid stroke="#21262d" strokeDasharray="3 4" vertical={false} />
              <XAxis dataKey="chartTime" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={{ stroke: '#30363d' }} tickLine={false} minTickGap={20} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} width={48} />
              <Tooltip contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 4, color: '#e6edf3' }} labelStyle={{ color: '#94a3b8' }} />
              <Legend wrapperStyle={{ color: '#94a3b8', fontSize: 11 }} />
              {dataKeys.map((key) => <Line key={key} type="monotone" dataKey={key} name={key.replace(/ \[[^\]]+\]$/, '')} stroke={seriesColors[key] ?? '#38bdf8'} strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />)}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Panel>
  );
}
