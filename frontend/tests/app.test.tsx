import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../src/App';

function event(machineId: string, offsetMs: number, predictedClass: 0 | 1, sessionId = 'session-1') {
  return {
    timestamp: new Date(Date.now() - 10_000 + offsetMs).toISOString(),
    session_id: sessionId,
    machine_id: machineId,
    simulation_mode: 'normal',
    simulated: true,
    Type: 'M',
    'Air temperature [K]': 300,
    'Process temperature [K]': 310,
    'Rotational speed [rpm]': 1500,
    'Torque [Nm]': 40,
    'Tool wear [min]': 100 + offsetMs / 100_000,
    predicted_class: predictedClass,
    predicted_label: predictedClass ? 'failure' : 'no failure',
    model_name: 'XGBoost',
    estimated_failure_probability: predictedClass ? 0.8 : 0.02,
  };
}

function managedAlert(alertId: string, machineId: string, status: 'active' | 'resolved', occurrenceCount: number, latest: ReturnType<typeof event>) {
  const timestamp = latest.timestamp;
  return {
    alert_id: alertId,
    session_id: 'session-1',
    machine_id: machineId,
    condition: 'failure_associated_prediction',
    simulation_mode: 'normal',
    first_seen: new Date(Date.now() - 20_000).toISOString(),
    created_at: new Date(Date.now() - 15_000).toISOString(),
    last_seen: timestamp,
    updated_at: timestamp,
    occurrence_count: occurrenceCount,
    status,
    resolved_at: status === 'resolved' ? timestamp : null,
    latest_event: latest,
  };
}

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  readyState = 0;

  constructor(readonly url: string) {
    MockWebSocket.instances.push(this);
  }

  open() {
    this.readyState = 1;
    this.onopen?.(new Event('open'));
  }

  emit(value: unknown) {
    this.onmessage?.({ data: JSON.stringify(value) } as MessageEvent);
  }

  disconnect() {
    this.readyState = 3;
    this.onclose?.(new CloseEvent('close'));
  }

  close() {
    if (this.readyState !== 3) this.disconnect();
  }
}

const first = event('SIM-A', 0, 0);
const second = event('SIM-B', 1_000, 1);
const latestA = event('SIM-A', 2_000, 0);
const activeAlert = managedAlert('SIM-B:failure_associated_prediction:1', 'SIM-B', 'active', 50, second);
const resolvedAlert = managedAlert('SIM-A:failure_associated_prediction:1', 'SIM-A', 'resolved', 12, latestA);

function installBackend({ unavailable = false, manyFailureEvents = false, authenticated = true } = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (unavailable) throw new Error('Backend offline');
    if (url.endsWith('/api/auth/session')) return { ok: true, json: async () => ({ authenticated, username: authenticated ? 'demo-user' : null }) };
    if (url.endsWith('/api/auth/login')) return { ok: true, json: async () => ({ authenticated: true, username: 'demo-user' }) };
    if (url.endsWith('/api/auth/register')) return { ok: true, status: 201, json: async () => ({ authenticated: true, username: 'new-user' }) };
    if (url.endsWith('/api/auth/logout')) return { ok: true, json: async () => ({ authenticated: false, username: null }) };
    const repeatedFailureEvents = manyFailureEvents
      ? Array.from({ length: 50 }, (_, index) => event('SIM-B', index * 10, 1))
      : [];
    const eventHistory = manyFailureEvents ? [first, ...repeatedFailureEvents, latestA] : [first, second, latestA];
    const snapshotActiveAlert = manyFailureEvents
      ? managedAlert(activeAlert.alert_id, 'SIM-B', 'active', 50, repeatedFailureEvents[repeatedFailureEvents.length - 1])
      : activeAlert;
    if (url.endsWith('/api/machines')) {
      return { ok: true, json: async () => ({ machine_count: 2, session_id: 'session-1', machines_with_readings: 2, machines: [
        { machine_id: 'SIM-A', latest_event: latestA }, { machine_id: 'SIM-B', latest_event: second },
      ] }) };
    }
    if (url.includes('/api/events')) return { ok: true, json: async () => ({ event_count: eventHistory.length, events: eventHistory }) };
    if (url.endsWith('/api/simulator/status')) return { ok: true, json: async () => ({ running: false, mode: 'normal', machine_count: 2, session_id: 'session-1', machine_ids: ['SIM-A', 'SIM-B'], active_machine_count: 0, session_event_count: eventHistory.length, historical_machine_count: 0, interval_seconds: 2, error: null }) };
    if (url.endsWith('/api/alerts')) return { ok: true, json: async () => ({ active_count: 1, resolved_count: 1, activation_threshold: 2, recovery_threshold: 3, alerts: [snapshotActiveAlert, resolvedAlert] }) };
    if (url.endsWith('/api/simulator/start')) {
      const body = JSON.parse(String(init?.body ?? '{}')) as { mode?: string; machine_count?: number };
      return { ok: true, json: async () => ({ running: true, mode: body.mode ?? 'normal', machine_count: body.machine_count ?? 3, session_id: 'session-2', machine_ids: Array.from({ length: body.machine_count ?? 3 }, (_, index) => `SIM-MACHINE-${String(index + 1).padStart(3, '0')}`), active_machine_count: body.machine_count ?? 3, session_event_count: 0, historical_machine_count: 2, interval_seconds: 2, error: null }) };
    }
    if (url.endsWith('/api/simulator/stop')) return { ok: true, json: async () => ({ running: false, mode: 'mixed', machine_count: 4, session_id: 'session-2', machine_ids: ['SIM-MACHINE-001', 'SIM-MACHINE-002', 'SIM-MACHINE-003', 'SIM-MACHINE-004'], active_machine_count: 0, session_event_count: 0, historical_machine_count: 2, interval_seconds: 2, error: null }) };
    throw new Error(`Unexpected backend URL: ${url}; method=${init?.method}`);
  });
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('WebSocket', MockWebSocket);
  MockWebSocket.instances = [];
  return fetchMock;
}

function renderApp() {
  return render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><App /></MemoryRouter>);
}

async function connectSocket(index = 0) {
  await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThan(index));
  act(() => MockWebSocket.instances[index].open());
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('backend-connected application', () => {
  it('shows the accessible login form for an unauthenticated session and signs in', async () => {
    const fetchMock = installBackend({ authenticated: false });
    renderApp();
    expect(await screen.findByRole('heading', { name: /Industrial Machine Failure/i })).toBeInTheDocument();
    expect(screen.getByLabelText('Username')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'demo-user' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'demo-password' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }));
    expect(await screen.findByRole('heading', { name: 'Machine Health Overview' })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/auth/login'), expect.objectContaining({ credentials: 'include' }));
  });

  it('logs out through the backend session and returns to the login page', async () => {
    const fetchMock = installBackend();
    renderApp();
    expect(await screen.findByRole('heading', { name: 'Machine Health Overview' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Sign out/i }));
    expect(await screen.findByRole('heading', { name: /Industrial Machine Failure/i })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/auth/logout'), expect.objectContaining({ method: 'POST', credentials: 'include' }));
  });

  it('validates sign-up confirmation and registers through the backend', async () => {
    const fetchMock = installBackend({ authenticated: false });
    renderApp();
    fireEvent.click(await screen.findByRole('link', { name: /Create an account/i }));
    expect(await screen.findByRole('heading', { name: /Create your account/i })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'new-user' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'safe-password' } });
    fireEvent.change(screen.getByLabelText('Confirm Password'), { target: { value: 'different-password' } });
    fireEvent.click(screen.getByRole('button', { name: /Create Account/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/do not match/i);
    fireEvent.change(screen.getByLabelText('Confirm Password'), { target: { value: 'safe-password' } });
    fireEvent.click(screen.getByRole('button', { name: /Create Account/i }));
    expect(await screen.findByRole('heading', { name: 'Machine Health Overview' })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/auth/register'), expect.objectContaining({ method: 'POST', credentials: 'include' }));
  });

  it('loads REST state and history, distinguishes event and machine counts, and reports true socket state', async () => {
    installBackend();
    renderApp();
    expect(await screen.findByRole('heading', { name: 'Machine Health Overview' })).toBeInTheDocument();
    const fleetKpis = document.querySelectorAll('.metrics-grid[aria-label="Fleet summary"] .metric-card');
    expect(fleetKpis).toHaveLength(4);
    expect(screen.getByText('Machines in Session')).toBeInTheDocument();
    expect(screen.getByText('Normal Predictions')).toBeInTheDocument();
    expect(screen.getByText('Attention Required')).toBeInTheDocument();
    expect(screen.getByText('Stale Machine Data')).toBeInTheDocument();
    expect(screen.queryByText('Machines with a reading')).not.toBeInTheDocument();
    expect(screen.queryByText('Active managed alerts')).not.toBeInTheDocument();
    expect(screen.getByText(/Backend: Disconnected/i)).toBeInTheDocument();
    await connectSocket();
    expect(await screen.findByText(/Backend: Connected/i)).toBeInTheDocument();
    expect(screen.getAllByText(/SIMULATED DATA/i).length).toBeGreaterThan(0);
    expect(document.querySelectorAll('.metric-value')[0]).toHaveTextContent('2');
    expect(document.querySelectorAll('.metric-value')[2]).toHaveTextContent('1');
    expect(screen.getByText(/2 machines in selected session · 3 events/i)).toBeInTheDocument();
    expect(screen.getByText(/Last successful update/i)).toBeInTheDocument();
  });

  it('applies WebSocket events, keeps latest machine counts, and ignores duplicate events', async () => {
    installBackend();
    renderApp();
    await screen.findByRole('heading', { name: 'Machine Health Overview' });
    await connectSocket();
    const incoming = event('SIM-A', 3_000, 1);
    act(() => MockWebSocket.instances[0].emit(incoming));
    await waitFor(() => expect(document.querySelectorAll('.metric-value')[2]).toHaveTextContent('2'));
    expect(screen.getByText(/2 machines in selected session · 4 events/i)).toBeInTheDocument();
    act(() => MockWebSocket.instances[0].emit(incoming));
    expect(screen.getByText(/2 machines in selected session · 4 events/i)).toBeInTheDocument();
  });

  it('switches all dashboard machine views to the newly selected session and ignores delayed old-session messages', async () => {
    installBackend();
    renderApp();
    await screen.findByRole('heading', { name: 'Machine Health Overview' });
    await connectSocket();
    fireEvent.click(screen.getByRole('button', { name: 'Start Normal Simulation' }));
    await waitFor(() => expect(document.querySelectorAll('.metric-value')[0]).toHaveTextContent('3'));
    expect(screen.queryByText('SIM-A')).not.toBeInTheDocument();
    expect(screen.getByText('SIM-MACHINE-001')).toBeInTheDocument();
    act(() => MockWebSocket.instances[0].emit(event('SIM-A', 4_000, 1, 'session-1')));
    expect(screen.queryByText('SIM-A')).not.toBeInTheDocument();
    expect(document.querySelectorAll('.metric-value')[0]).toHaveTextContent('3');
  });

  it('shows managed alert episodes and counts the active badge by machine condition', async () => {
    installBackend({ manyFailureEvents: true });
    renderApp();
    await screen.findByRole('heading', { name: 'Machine Health Overview' });
    const alertLink = screen.getByRole('link', { name: /Alerts & Notifications/i });
    expect(alertLink.querySelector('.nav-count')).toHaveTextContent('1');
    expect(alertLink.querySelector('.nav-count')).toHaveAttribute('aria-label', '1 active alerts');
    expect(screen.getByText(/2 machines in selected session · 53 events/i)).toBeInTheDocument();
    fireEvent.click(alertLink);
    expect(await screen.findByRole('heading', { name: 'Alerts & Notifications' })).toBeInTheDocument();
    expect(screen.getByText('Active alerts')).toBeInTheDocument();
    expect(screen.getByText('Resolved alerts')).toBeInTheDocument();
    expect(screen.getAllByText(/associated class 1 readings/i)).toHaveLength(2);
    expect(screen.getByText('50 associated class 1 readings')).toBeInTheDocument();
    expect(document.querySelectorAll('.alert-card')).toHaveLength(2);
    await connectSocket();
    const changedAlert = { ...activeAlert, occurrence_count: 51, updated_at: new Date(Date.now() + 1).toISOString(), last_seen: new Date(Date.now() + 1).toISOString() };
    act(() => MockWebSocket.instances[0].emit({ event_type: 'alert.updated', alert: changedAlert }));
    expect(await screen.findByText('51 associated class 1 readings')).toBeInTheDocument();
    expect(document.querySelectorAll('.alert-card')).toHaveLength(2);
  });

  it('rejects invalid WebSocket events without presenting them as current data', async () => {
    installBackend();
    renderApp();
    await screen.findByRole('heading', { name: 'Machine Health Overview' });
    await connectSocket();
    act(() => MockWebSocket.instances[0].emit({ ...event('SIM-C', 4_000, 1), 'Product ID': 'excluded' }));
    expect(await screen.findByText(/1 invalid backend event was ignored/i)).toBeInTheDocument();
    expect(screen.queryByText('SIM-C')).not.toBeInTheDocument();
  });

  it('shows reconnecting after a real disconnect and returns to connected only after reopen', async () => {
    const fetchMock = installBackend();
    renderApp();
    await screen.findByRole('heading', { name: 'Machine Health Overview' });
    await connectSocket();
    expect(await screen.findByText(/Backend: Connected/i)).toBeInTheDocument();
    act(() => MockWebSocket.instances[0].disconnect());
    expect(await screen.findByText(/Backend: Reconnecting/i)).toBeInTheDocument();
    await connectSocket(1);
    expect(await screen.findByText(/Backend: Connected/i)).toBeInTheDocument();
    await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/api/machines')).length).toBeGreaterThan(1));
  });

  it('shows a retryable backend error without using the fixed fixture', async () => {
    const fetchMock = installBackend({ unavailable: true });
    renderApp();
    expect(await screen.findByRole('alert')).toHaveTextContent(/Backend offline/);
    expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/'), expect.anything());
    const previousCallCount = fetchMock.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: /Retry/i }));
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(previousCallCount));
    expect(await screen.findByRole('alert')).toHaveTextContent(/Backend offline/);
  });

  it('starts and stops the backend simulator through explicit REST controls', async () => {
    const fetchMock = installBackend();
    renderApp();
    await screen.findByRole('heading', { name: 'Machine Health Overview' });
    fireEvent.change(screen.getByRole('combobox', { name: 'Simulation mode' }), { target: { value: 'mixed' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Number of simulated machines' }), { target: { value: '4' } });
    fireEvent.click(screen.getByRole('button', { name: 'Start Mixed Simulation' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8000/api/simulator/start', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ mode: 'mixed', machine_count: 4 }),
    })));
    expect(await screen.findByRole('button', { name: 'Stop simulator' })).toBeInTheDocument();
    expect(screen.getByText(/Mixed · 4 machines · 2s/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Stop simulator' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8000/api/simulator/stop', expect.objectContaining({ method: 'POST' })));
  });

  it('navigates among all four pages with backend telemetry state shared', async () => {
    installBackend();
    renderApp();
    await screen.findByRole('heading', { name: 'Machine Health Overview' });
    await connectSocket();
    fireEvent.click(screen.getByRole('link', { name: /Live Machine Monitoring/i }));
    expect(await screen.findByRole('heading', { name: 'Live Machine Monitoring' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('link', { name: /Failure Prediction & Analysis/i }));
    expect(await screen.findByRole('heading', { name: 'Failure Prediction & Analysis' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('link', { name: /Alerts & Notifications/i }));
    expect(await screen.findByRole('heading', { name: 'Alerts & Notifications' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('link', { name: /Operations Overview/i }));
    expect(await screen.findByRole('heading', { name: 'Machine Health Overview' })).toBeInTheDocument();
  });
});
