import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { api, ApiError, loadSession, ROLE_RANK, saveSession, type Role, type Session } from "./api";

interface AuthValue {
  session: Session | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  call: <T>(path: string, init?: RequestInit) => Promise<T>;
  atLeast: (role: Role) => boolean;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(loadSession);

  const logout = useCallback(() => {
    saveSession(null);
    setSession(null);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api<{ access_token: string; role: Role; email: string }>("/auth/login", null, {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    const s = { token: r.access_token, role: r.role, email: r.email };
    saveSession(s);
    setSession(s);
  }, []);

  const call = useCallback(
    async <T,>(path: string, init?: RequestInit) => {
      try {
        return await api<T>(path, session?.token ?? null, init);
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) logout();
        throw e;
      }
    },
    [session, logout],
  );

  const atLeast = useCallback((role: Role) => !!session && ROLE_RANK[session.role] >= ROLE_RANK[role], [session]);

  const value = useMemo(() => ({ session, login, logout, call, atLeast }), [session, login, logout, call, atLeast]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
