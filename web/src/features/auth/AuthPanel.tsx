import { useEffect, useState, type FormEvent } from "react";
import { api, type AuthIdentity } from "../../api";

export function AuthPanel({ onToken, onIdentity }: { onToken: () => void; onIdentity?: (identity: AuthIdentity | null) => void }) {
  const [identity, setIdentity] = useState<AuthIdentity | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void api.me().then((value) => { setIdentity(value); onIdentity?.(value); }).catch(() => onIdentity?.(null));
  }, [onIdentity]);
  const login = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setMessage(null);
    try { await api.login(username.trim(), password); const value = await api.me(); setIdentity(value); onIdentity?.(value); setPassword(""); onToken(); }
    catch (cause) { setMessage(cause instanceof Error ? cause.message : "Sign-in failed"); }
    finally { setBusy(false); }
  };
  const logout = async () => { try { await api.logout(); } catch { /* expired sessions are already logged out */ } setIdentity(null); onIdentity?.(null); onToken(); };
  return <section className="auth-panel" aria-label="Authentication"><h2>Authentication</h2>{identity ? <><p className="muted">Signed in as {identity.username} ({identity.role})</p><button className="preview" onClick={() => void logout()}>Sign out</button></> : <form onSubmit={(event) => void login(event)}><label>Username<input aria-label="Username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required /></label><label>Password<input aria-label="Password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label><button className="preview" type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>{message && <p className="error" role="alert">{message}</p>}</form>}</section>;
}
