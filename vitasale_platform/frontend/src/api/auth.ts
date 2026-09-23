import axios from "axios";
import { setAccessToken, setRefreshToken } from "./client";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";

export async function login(username: string, password: string): Promise<void> {
  const resp = await axios.post(`${API_BASE}/auth/token/`, { username, password });
  setAccessToken(resp.data.access);
  setRefreshToken(resp.data.refresh);
}

export function logout(): void {
  setAccessToken(null);
  setRefreshToken(null);
}
