import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { formatParams, type AgentStep, type Approval } from "../api";
import { useAuth } from "../auth";
import { useChat } from "../chat";
import Markdown from "../components/Markdown";
import { Button, ErrorNote, PageHeader, Status, STATUS_COLOR } from "../components/ui";

const STARTERS = [
  "Order 1042 still hasn't been charged. Find out why and fix it.",
  "Give me a quick health check of the fleet.",
  "Is anything in the dead-letter queue?",
];

const REQUEST_LABEL: Record<string, string> = {
  pending: "awaiting approval",
  executing: "running",
  executed: "approved and ran",
  failed: "approved, then failed",
  rejected: "rejected",
  cancelled: "cancelled",
};

function ToolTrace({ steps, approvals }: { steps: AgentStep[]; approvals: Map<number, string> }) {
  if (!steps.length) return null;
  return (
    <details className="mt-3" open={steps.some((s) => s.approval_id)}>
      <summary className="cursor-pointer text-sm text-ink-soft">
        {steps.length} tool call{steps.length > 1 ? "s" : ""}
      </summary>
      <ol className="mt-2 flex flex-col gap-1">
        {steps.map((s, i) => {
          // For approval requests, show where the request stands now, not when the agent made it.
          const current = s.approval_id ? approvals.get(s.approval_id) : undefined;
          const holder = current ? STATUS_COLOR[current] : STATUS_COLOR[s.status];
          return (
            <li
              key={i}
              className="strip grid gap-x-4 py-1.5 pr-3 pl-5 text-sm sm:grid-cols-[180px_1fr_auto]"
              style={{ ["--holder" as string]: holder ?? "var(--color-ink-soft)" }}
            >
              <span className="font-strip text-base font-semibold">{s.tool}</span>
              <span className="truncate text-ink-soft" title={formatParams(s.args)}>{formatParams(s.args) || "no arguments"}</span>
              <span className="flex items-center gap-3">
                {current ? (
                  <span className="inline-flex items-center gap-1.5 text-sm font-medium whitespace-nowrap">
                    <span aria-hidden className="size-2.5 rounded-full" style={{ background: holder }} />
                    {REQUEST_LABEL[current] ?? current}
                  </span>
                ) : (
                  <Status value={s.status} />
                )}
                {s.approval_id && (
                  <Link to="/approvals" className="font-semibold text-hold underline underline-offset-4">
                    Request #{s.approval_id}
                  </Link>
                )}
              </span>
            </li>
          );
        })}
      </ol>
    </details>
  );
}

export default function Copilot() {
  const { call, session } = useAuth();
  const { turns, busy, error, send, reset } = useChat();
  const [draft, setDraft] = useState("");
  const [approvals, setApprovals] = useState<Map<number, string>>(new Map());
  const endRef = useRef<HTMLDivElement>(null);

  const hasRequests = turns.some((t) => t.steps?.some((s) => s.approval_id));
  const refreshApprovals = useCallback(() => {
    call<Approval[]>("/approvals?status=")
      .then((rows) => setApprovals(new Map(rows.map((a) => [a.id, a.status]))))
      .catch(() => {});
  }, [call]);

  useEffect(() => {
    if (!hasRequests) return;
    refreshApprovals();
    const t = setInterval(refreshApprovals, 8000);
    return () => clearInterval(t);
  }, [hasRequests, refreshApprovals, turns.length]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, busy]);

  function submit(e: FormEvent) {
    e.preventDefault();
    send(draft);
    setDraft("");
  }

  return (
    <>
      <PageHeader title="Copilot">
        <div className="flex max-w-md flex-col items-end gap-2">
          <p className="text-sm text-ink-soft">
            Acting as {session?.email} ({session?.role}). The agent only sees tools your role allows, and destructive
            actions become approval requests.
          </p>
          {turns.length > 0 && (
            <Button tone="quiet" onClick={reset} disabled={busy}>New conversation</Button>
          )}
        </div>
      </PageHeader>

      <div className="flex flex-col gap-5" aria-live="polite">
        {turns.length === 0 && (
          <div>
            <p className="mb-3 text-ink-soft">Describe what you are seeing. Some places to start:</p>
            <div className="flex flex-col gap-2">
              {STARTERS.map((s) => (
                <button key={s} onClick={() => send(s)} disabled={busy} className="strip py-2 pr-4 pl-6 text-left hover:bg-white">
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
              <Markdown text={t.content} />
              <ToolTrace steps={t.steps ?? []} approvals={approvals} />
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
