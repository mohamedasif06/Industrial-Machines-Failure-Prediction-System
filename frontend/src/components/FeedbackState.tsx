import { AlertCircle, LoaderCircle, RefreshCw, Radio } from 'lucide-react';

export function LoadingState() {
  return <div className="feedback-state" role="status"><LoaderCircle className="spin" size={20} /><span>Loading telemetry from the backend…</span></div>;
}

export function EmptyState({ title = 'No telemetry events available', detail = 'There are no valid readings to show yet. Start the simulator to generate synthetic events.' }: { title?: string; detail?: string }) {
  return <div className="feedback-state feedback-empty"><Radio size={21} /><div><strong>{title}</strong><p>{detail}</p></div></div>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="feedback-state feedback-error" role="alert">
      <AlertCircle size={20} /><span>{message}</span>
      <button className="button button-secondary button-small" onClick={onRetry}><RefreshCw size={14} />Retry</button>
    </div>
  );
}
