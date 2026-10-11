import type { LucideIcon } from 'lucide-react';

export function MetricCard({ label, value, detail, Icon, tone = 'blue' }: {
  label: string;
  value: string | number;
  detail: string;
  Icon: LucideIcon;
  tone?: 'blue' | 'green' | 'amber' | 'slate';
}) {
  return (
    <article className="metric-card">
      <div className={`metric-icon metric-icon-${tone}`}><Icon aria-hidden="true" size={18} /></div>
      <p className="eyebrow">{label}</p>
      <p className="metric-value">{value}</p>
      <p className="metric-detail">{detail}</p>
    </article>
  );
}
