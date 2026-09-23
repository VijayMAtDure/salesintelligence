import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api/auth";
import { useAuth } from "../api/AuthContext";

export function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { setAuthenticated } = useAuth();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password);
      // must flip the SHARED auth state, not just navigate — RequireAuth reads this same
      // context, and navigating without updating it just bounces straight back to /login
      // (the exact bug browser-automation testing caught).
      setAuthenticated(true);
      navigate("/ingestion");
    } catch {
      setError("Invalid username or password.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "center",
      minHeight: "100vh", background: "#f8fafc", fontFamily: "system-ui, sans-serif",
    }}>
      <form onSubmit={handleSubmit} style={{
        background: "#fff", padding: 32, borderRadius: 8, width: 320,
        boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
      }}>
        <h2 style={{ marginTop: 0, fontSize: 18 }}>VITASale Sales Intelligence</h2>
        <label style={{ display: "block", fontSize: 13, marginBottom: 4 }}>Username</label>
        <input
          value={username} onChange={(e) => setUsername(e.target.value)}
          style={{ width: "100%", padding: 8, marginBottom: 12, border: "1px solid #cbd5e1", borderRadius: 4 }}
        />
        <label style={{ display: "block", fontSize: 13, marginBottom: 4 }}>Password</label>
        <input
          type="password" value={password} onChange={(e) => setPassword(e.target.value)}
          style={{ width: "100%", padding: 8, marginBottom: 16, border: "1px solid #cbd5e1", borderRadius: 4 }}
        />
        {error && <p style={{ color: "#ef4444", fontSize: 13 }}>{error}</p>}
        <button
          type="submit" disabled={loading}
          style={{
            width: "100%", padding: 10, background: "#334155", color: "#fff",
            border: "none", borderRadius: 4, fontWeight: 600, cursor: "pointer",
          }}
        >
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  );
}
