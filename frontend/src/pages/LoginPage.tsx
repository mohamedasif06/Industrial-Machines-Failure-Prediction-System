import { Activity, KeyRound } from 'lucide-react';
import { FormEvent, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../services/auth';

export function LoginPage() {
  const { login, refresh, state } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(null); setSubmitting(true);
    try { await login(username, password); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Sign in failed.'); }
    finally { setSubmitting(false); }
  }
  return <main className="login-page">
    <section className="login-card" aria-labelledby="login-title">
      <div className="login-mark"><Activity size={25} /></div>
      <p className="eyebrow">SECURE OPERATIONS ACCESS</p>
      <h1 id="login-title">Industrial Machine<br />Failure Forecasting System</h1>
      <p className="login-caption">Sign in to view simulated telemetry and model predictions.</p>
      {state.error && <div className="login-error" role="alert">{state.error}</div>}
      {state.error && <button className="button login-retry" type="button" onClick={() => void refresh()} disabled={state.loading}>Retry connection</button>}
      {error && <div className="login-error" role="alert">{error}</div>}
      <form onSubmit={submit}>
        <label htmlFor="username">Username</label>
        <input id="username" name="username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required disabled={submitting} />
        <label htmlFor="password">Password</label>
        <input id="password" name="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required disabled={submitting} />
        <button className="button login-button" type="submit" disabled={submitting}><KeyRound size={16} />{submitting ? 'Signing in…' : 'Sign In'}</button>
      </form>
      <p className="login-footnote">New user? <Link to="/signup">Create an account</Link></p>
    </section>
  </main>;
}
