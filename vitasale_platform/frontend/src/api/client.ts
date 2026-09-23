/**
 * Axios client with JWT auth. Access token lives in memory (a module-level variable, lost on
 * page refresh — acceptable for this stage of the project); refresh token in localStorage.
 *
 * KNOWN FOLLOW-UP (not done): architecture doc §5.4 originally called for an httpOnly cookie
 * for the refresh token. That needs backend support SimpleJWT doesn't provide out of the box
 * (it returns tokens in the response body, not Set-Cookie headers) — deferred rather than
 * half-implemented. localStorage is the pragmatic interim choice, not the final one.
 */
import axios, { type AxiosError } from "axios";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";

let accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getRefreshToken(): string | null {
  return localStorage.getItem("refresh_token");
}

export function setRefreshToken(token: string | null) {
  if (token) localStorage.setItem("refresh_token", token);
  else localStorage.removeItem("refresh_token");
}

export const apiClient = axios.create({ baseURL: API_BASE });

apiClient.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

let refreshingPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const refresh = getRefreshToken();
  if (!refresh) throw new Error("no refresh token");
  const resp = await axios.post(`${API_BASE}/auth/token/refresh/`, { refresh });
  const newAccess = resp.data.access as string;
  setAccessToken(newAccess);
  return newAccess;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config;
    if (error.response?.status === 401 && original && !(original as any)._retried) {
      (original as any)._retried = true;
      try {
        // de-dupe concurrent 401s into a single refresh call
        refreshingPromise ??= refreshAccessToken().finally(() => {
          refreshingPromise = null;
        });
        const newToken = await refreshingPromise;
        original.headers = original.headers ?? {};
        original.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(original);
      } catch {
        setAccessToken(null);
        setRefreshToken(null);
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);
