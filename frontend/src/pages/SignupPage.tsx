import { Activity, KeyRound } from 'lucide-react';
import { FormEvent, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../services/auth';

export function SignupPage() {
  const { signUp } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (password !== confirmation) { setError('Passwords do not match.'); return; }
    setSubmitting(true);
    try { await signUp(username, password); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not create the account.'); }
    finally { setSubmitting(false); }
  }

  return <main className="login-page">
    <section className="login-card" aria-labelledby="signup-title">
      <div className="login-mark"><Activity size={25} /></div>
      <p className="eyebrow">SECURE OPERATIONS ACCESS</p>
      <h1 id="signup-title">Create your account</h1>
      <p className="login-caption">Register to view simulated telemetry and model predictions.</p>
      {error && <div className="login-error" role="alert">{error}</div>}
      <form onSubmit={submit}>
        <label htmlFor="signup-username">Username</label>
        <input id="signup-username" name="username" autoComplete="username" minLength={3} maxLength={50} pattern="[A-Za-z0-9_.-]+" value={username} onChange={(event) => setUsername(event.target.value)} required disabled={submitting} />
        <label htmlFor="signup-password">Password</label>
        <input id="signup-password" name="password" type="password" autoComplete="new-password" minLength={8} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} required disabled={submitting} />
        <label htmlFor="signup-confirmation">Confirm Password</label>
        <input id="signup-confirmation" name="confirmation" type="password" autoComplete="new-password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required disabled={submitting} />
        <button className="button login-button" type="submit" disabled={submitting}><KeyRound size={16} />{submitting ? 'Creating account…' : 'Create Account'}</button>
      </form>
      <p className="login-footnote">Already registered? <Link to="/login">Sign in</Link></p>
    </section>
  </main>;
}
