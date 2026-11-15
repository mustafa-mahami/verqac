import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { api, refreshSession, setAccessToken, type Me } from './api';

interface AuthState {
  me: Me | null;
  loading: boolean;
  signIn: (accessToken: string) => Promise<void>;
  signOut: () => Promise<void>;
  reload: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try {
      setMe(await api<Me>('/auth/me'));
    } catch {
      setMe(null);
    }
  }, []);

  useEffect(() => {
    // a page reload keeps the session through the refresh cookie
    refreshSession()
      .then((ok) => (ok ? reload() : setMe(null)))
      .finally(() => setLoading(false));
  }, [reload]);

  const signIn = async (token: string) => {
    setAccessToken(token);
    await reload();
  };

  const signOut = async () => {
    await api('/auth/logout', { method: 'POST' }).catch(() => undefined);
    setAccessToken(null);
    setMe(null);
  };

  return <AuthContext.Provider value={{ me, loading, signIn, signOut, reload }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth outside AuthProvider');
  return ctx;
}
