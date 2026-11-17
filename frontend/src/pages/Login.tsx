import { useState, type FormEvent } from "react";
import { useAuth } from "../auth";
import { Button, ErrorNote } from "../components/ui";

const DEMO = [
  { email: "viewer@opspilot.dev", role: "Viewer", can: "Read-only tools" },
  { email: "engineer@opspilot.dev", role: "Engineer", can: "Requests restarts, flags, replays" },
  { email: "sre@opspilot.dev", role: "SRE", can: "Requests rollbacks, approves most actions" },
  { email: "admin@opspilot.dev", role: "Admin", can: "Approves rollbacks, replays scenarios" },
];

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("engineer@opspilot.dev");
  const [password, setPassword] = useState("password");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto grid min-h-screen max-w-4xl content-center gap-10 px-4 py-10 md:grid-cols-[1fr_1fr]">
      <div>
        <h1 className="font-strip text-6xl font-bold tracking-tight">OpsPilot</h1>
        <p className="mt-3 max-w-sm text-lg text-ink-soft">
          Ask about an incident in plain English. The agent investigates with real tools, and anything risky waits for a
          human to approve it.
        </p>
      </div>
      <form onSubmit={submit} className="strip strip-in flex flex-col gap-4 py-6 pr-6 pl-8" style={{ ["--holder" as string]: "var(--color-hold)" }}>
        {error && <ErrorNote message={error} />}
        <label className="flex flex-col gap-1 text-sm font-medium">
          Email
          <input className="border border-strip-edge bg-white px-3 py-2 text-base" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          Password
          <input className="border border-strip-edge bg-white px-3 py-2 text-base" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        </label>
        <Button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
        <fieldset className="mt-2">
          <legend className="mb-2 text-sm text-ink-soft">Demo accounts (password: password)</legend>
          <div className="grid gap-1">
            {DEMO.map((d) => (
              <button
                type="button"
                key={d.email}
                onClick={() => setEmail(d.email)}
                aria-pressed={email === d.email}
                className={`flex justify-between gap-3 px-2 py-1 text-left text-sm ${email === d.email ? "bg-board" : "hover:bg-board/60"}`}
              >
                <span className="font-semibold">{d.role}</span>
                <span className="text-ink-soft">{d.can}</span>
              </button>
            ))}
          </div>
        </fieldset>
      </form>
    </div>
  );
}
