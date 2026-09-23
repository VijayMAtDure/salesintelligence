import { createContext, useContext, useEffect, useState } from "react";
import axios from "axios";
import { getRefreshToken, setAccessToken, setRefreshToken } from "./client";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";

interface AuthState {
  ready: boolean;
  authenticated: boolean;
  setAuthenticated: (v: boolean) => void;
}

const AuthCtx = createContext<AuthState | null>(null);

/**
 * Login screen removed from the UI per explicit request ("we do not need login part as of
 * now on UI") — but the backend's JWT auth is left fully intact rather than stripped out,
 * since this was framed as "as of now," a showcase-stage simplification, not a permanent
 * decision. Every API call is still a real authenticated request; it's just acquired
 * silently here instead of typed into a visible form.
 *
 * ⚠️ DEV-ONLY. Credentials come from VITE_DEV_AUTO_LOGIN_* env vars (frontend/.env), which
 * means they end up readable in the built JS bundle — fine for an internal showcase behind
 * this box's own firewall, NOT fine for anything internet-facing. Re-enabling the visible
 * LoginPage (still present, just unrouted — see App.tsx) is the reversal path.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    async function restoreOrAutoLogin() {
      const refresh = getRefreshToken();
      if (refresh) {
        try {
          const resp = await axios.post(`${API_BASE}/auth/token/refresh/`, { refresh });
          setAccessToken(resp.data.access);
          setAuthenticated(true);
          return;
        } catch {
          // stale/expired refresh token — fall through to auto-login
        }
      }

      const devUser = import.meta.env.VITE_DEV_AUTO_LOGIN_USERNAME;
      const devPass = import.meta.env.VITE_DEV_AUTO_LOGIN_PASSWORD;
      if (devUser && devPass) {
        try {
          const resp = await axios.post(`${API_BASE}/auth/token/`, {
            username: devUser, password: devPass,
          });
          setAccessToken(resp.data.access);
          setRefreshToken(resp.data.refresh);
          setAuthenticated(true);
        } catch {
          setAuthenticated(false);
        }
      }
    }

    restoreOrAutoLogin().finally(() => setReady(true));
  }, []);

  return (
    <AuthCtx.Provider value={{ ready, authenticated, setAuthenticated }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
