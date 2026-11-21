import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api } from './api.js';

// Who is signed in and what role they have. `me` is undefined while checking,
// { authenticated: false } for visitors, or { name, role, home } for users.
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [me, setMe] = useState(undefined);

  const refresh = useCallback(async () => {
    try {
      const res = await api.me();
      setMe(res || { authenticated: false });
      return res;
    } catch {
      setMe({ authenticated: false });
      return { authenticated: false };
    }
  }, []);

  const signOut = useCallback(async () => {
    await api.logout().catch(() => {});
    setMe({ authenticated: false });
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  // A request came back "please sign in": the session ended (expired, signed out elsewhere,
  // account switched off). Re-check, so the page guards send the person to sign in.
  useEffect(() => {
    const onUnauthorized = () => { refresh(); };
    window.addEventListener('sp:unauthorized', onUnauthorized);
    return () => window.removeEventListener('sp:unauthorized', onUnauthorized);
  }, [refresh]);

  return <AuthContext.Provider value={{ me, refresh, signOut }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);

/** Send a user to their own screen: React paths stay in the app, others leave it. */
export function goHome(navigate, home) {
  if (!home) return navigate('/');
  if (home.startsWith('/')) return navigate(home, { replace: true });
  window.location.assign(home);
}

export const ROLE_LABELS = {
  director: 'Director', sales: 'Sales', support: 'Support', warehouse: 'Warehouse',
  technician: 'Technician', customer: 'Customer', staff: 'Staff'
};
