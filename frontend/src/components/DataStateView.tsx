import { useTelemetry } from '../hooks/useTelemetry';
import { EmptyState, ErrorState, LoadingState } from './FeedbackState';

export function DataStateView() {
  const { loading, error, events, rejectedCount, reload } = useTelemetry();
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (events.length === 0) return <EmptyState />;
  if (rejectedCount > 0) return <div className="notice notice-warning" role="status">{rejectedCount} invalid backend event{rejectedCount === 1 ? ' was' : 's were'} ignored. Valid events remain available below.</div>;
  return null;
}
