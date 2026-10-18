import { createContext, useContext } from 'react';

const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim();
export const AUTH_API_BASE_URL = (configuredBase || 'http://127.0.0.1:8000').replace(/\/+$/, '');

export interface AuthUser { username: string; }
export interface AuthState { loading: boolean; user: AuthUser | null; error: string | null; }

export async function getSession(): Promise<AuthUser | null> {
  const response = await fetch(`${AUTH_API_BASE_URL}/api/auth/session`, { credentials: 'include', headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error('Could not check the backend session.');
  const body = await response.json() as { authenticated?: boolean; username?: string | null };
  return body.authenticated && typeof body.username === 'string' ? { username: body.username } : null;
}

export async function signIn(username: string, password: string): Promise<AuthUser> {
  const response = await fetch(`${AUTH_API_BASE_URL}/api/auth/login`, {
    method: 'POST', credentials: 'include',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (response.status === 401) throw new Error('Invalid username or password.');
  if (!response.ok) throw new Error('The authentication service is unavailable.');
  const body = await response.json() as { authenticated?: boolean; username?: string };
  if (!body.authenticated || typeof body.username !== 'string') throw new Error('The authentication service returned an invalid response.');
  return { username: body.username };
}

export async function signUp(username: string, password: string): Promise<AuthUser> {
  const response = await fetch(`${AUTH_API_BASE_URL}/api/auth/register`, {
    method: 'POST', credentials: 'include',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (response.status === 409) throw new Error('That username is already registered.');
  if (response.status === 422) throw new Error('Use a valid username and password.');
  if (!response.ok) throw new Error('The registration service is unavailable.');
  const body = await response.json() as { authenticated?: boolean; username?: string };
  if (!body.authenticated || typeof body.username !== 'string') throw new Error('The registration service returned an invalid response.');
  return { username: body.username };
}

export async function signOut(): Promise<void> {
  const response = await fetch(`${AUTH_API_BASE_URL}/api/auth/logout`, { method: 'POST', credentials: 'include', headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error('Could not sign out from the backend.');
}

export const AuthContext = createContext<{
  state: AuthState;
  refresh: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  signUp: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
} | null>(null);

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider.');
  return value;
}
