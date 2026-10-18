import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { AuthContext, getSession, signIn, signOut, signUp, type AuthState } from '../services/auth';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ loading: true, user: null, error: null });
  const refresh = useCallback(async () => {
    setState((current) => ({ ...current, loading: true, error: null }));
    try { setState({ loading: false, user: await getSession(), error: null }); }
    catch (error) { setState({ loading: false, user: null, error: error instanceof Error ? error.message : 'Could not reach the authentication service.' }); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const login = useCallback(async (username: string, password: string) => {
    const user = await signIn(username, password);
    setState({ loading: false, user, error: null });
  }, []);
  const register = useCallback(async (username: string, password: string) => {
    const user = await signUp(username, password);
    setState({ loading: false, user, error: null });
  }, []);
  const logout = useCallback(async () => { await signOut(); setState({ loading: false, user: null, error: null }); }, []);
  const value = useMemo(() => ({ state, refresh, login, signUp: register, logout }), [state, refresh, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
