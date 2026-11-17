import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { formatParams, type AgentStep, type ChatReply } from "../api";
import { useAuth } from "../auth";
import { Button, ErrorNote, PageHeader, Status, STATUS_COLOR } from "../components/ui";

interface Turn {
  role: "user" | "assistant";
  content: string;
  steps?: AgentStep[];
}

const STARTERS = [
  "Order 1042 still hasn't been charged. Find out why and fix it.",
  "Give me a quick health check of the fleet.",
  "Is anything in the dead-letter queue?",
];

function ToolTrace({ steps }: { steps: AgentStep[] }) {
  if (!steps.length) return null;
  return (
    <details className="mt-3" open={steps.some((s) => s.approval_id)}>
      <summary className="cursor-pointer text-sm text-ink-soft">
        {steps.length} tool call{steps.length > 1 ? "s" : ""}
      </summary>
      <ol className="mt-2 flex flex-col gap-1">
        {steps.map((s, i) => (
          <li
            key={i}
            className="strip grid gap-x-4 py-1.5 pr-3 pl-5 text-sm sm:grid-cols-[180px_1fr_auto]"
            style={{ ["--holder" as string]: STATUS_COLOR[s.status] ?? "var(--color-ink-soft)" }}
          >
            <span className="font-strip text-base font-semibold">{s.tool}</span>
            <span className="truncate text-ink-soft" title={formatParams(s.args)}>{formatParams(s.args) || "no arguments"}</span>
            <span className="flex items-center gap-3">
              <Status value={s.status} />
              {s.approval_id && (
                <Link to="/approvals" className="font-semibold text-hold underline underline-offset-4">
                  Request #{s.approval_id}
                </Link>
              )}
            </span>
          </li>
        ))}
      </ol>
    </details>
  );
}

export default function Copilot() {
  const { call, session } = useAuth();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, busy]);

  async function send(text: string) {
    const content = text.trim();
    if (!content || busy) return;
    const history = [...turns, { role: "user" as const, content }];
    setTurns(history);
    setDraft("");
    setBusy(true);
    setError("");
    try {
      const r = await call<ChatReply>("/chat", {
        method: "POST",
        body: JSON.stringify({ messages: history.map(({ role, content }) => ({ role, content })) }),
      });
      setTurns([...history, { role: "assistant", content: r.reply, steps: r.steps }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The agent did not respond");
    } finally {
      setBusy(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    send(draft);
  }

  return (
    <>
      <PageHeader title="Copilot">
        <p className="max-w-md text-sm text-ink-soft">
          Acting as {session?.email} ({session?.role}). The agent only sees tools your role allows, and destructive
          actions become approval requests.
        </p>
      </PageHeader>

      <div className="flex flex-col gap-5" aria-live="polite">
        {turns.length === 0 && (
          <div>
            <p className="mb-3 text-ink-soft">Describe what you are seeing. Some places to start:</p>
            <div className="flex flex-col gap-2">
              {STARTERS.map((s) => (
                <button key={s} onClick={() => send(s)} className="strip py-2 pr-4 pl-6 text-left hover:bg-white">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((t, i) =>
          t.role === "user" ? (
            <p key={i} className="max-w-2xl self-end bg-ink px-4 py-2.5 text-strip">{t.content}</p>
          ) : (
            <div key={i} className="max-w-3xl">
              <p className="whitespace-pre-wrap leading-relaxed">{t.content}</p>
              <ToolTrace steps={t.steps ?? []} />
            </div>
          ),
        )}
        {busy && <p className="text-ink-soft">Investigating…</p>}
        {error && <ErrorNote message={error} />}
        <div ref={endRef} />
      </div>

      <form onSubmit={submit} className="sticky bottom-0 mt-6 flex gap-2 bg-board py-4">
        <label htmlFor="ask" className="sr-only">Message</label>
        <input
          id="ask"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Why are payments failing?"
          className="min-w-0 flex-1 border border-strip-edge bg-strip px-4 py-2.5"
          disabled={busy}
        />
        <Button type="submit" disabled={busy || !draft.trim()}>Send</Button>
      </form>
    </>
  );
}
