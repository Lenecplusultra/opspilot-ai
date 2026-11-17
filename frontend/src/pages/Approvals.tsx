import { useCallback, useEffect, useState } from "react";
import { formatParams, minutesAgo, ROLE_RANK, type Approval } from "../api";
import { useAuth } from "../auth";
import { Button, ErrorNote, PageHeader, Status, STATUS_COLOR } from "../components/ui";

const FILTERS = [
  { value: "pending", label: "Pending" },
  { value: "", label: "All" },
];

export default function Approvals() {
  const { call, session, atLeast } = useAuth();
  const [filter, setFilter] = useState("pending");
  const [rows, setRows] = useState<Approval[] | null>(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(() => {
    call<Approval[]>(`/approvals?status=${filter}`).then(setRows).catch((e) => setError(e.message));
  }, [call, filter]);

  useEffect(() => {
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load]);

  async function decide(a: Approval, approve: boolean) {
    setBusyId(a.id);
    setError("");
    try {
      await call(`/approvals/${a.id}/${approve ? "approve" : "reject"}`, { method: "POST" });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Decision failed");
    } finally {
      setBusyId(null);
    }
  }

  const canDecide = (a: Approval) =>
    !!session && a.status === "pending" && ROLE_RANK[session.role] >= ROLE_RANK[a.approver_role] && a.requested_by !== session.email;

  return (
    <>
      <PageHeader title="Approvals">
        <div role="group" aria-label="Filter" className="flex">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              aria-pressed={filter === f.value}
              className={`border border-ink/30 px-3 py-1 font-strip text-base font-semibold ${filter === f.value ? "bg-ink text-strip" : "hover:bg-strip"}`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </PageHeader>
      {!atLeast("sre") && (
        <p className="mb-4 text-sm text-ink-soft">You see your own requests. SREs and admins see and decide the whole queue.</p>
      )}
      {error && <ErrorNote message={error} />}
      {rows && rows.length === 0 && (
        <p className="text-ink-soft">
          {filter === "pending" ? "Nothing is waiting for a decision." : "No requests yet. Destructive actions requested through the Copilot show up here."}
        </p>
      )}
      <ol className="flex flex-col gap-2">
        {rows?.map((a) => (
          <li
            key={a.id}
            className="strip grid gap-x-6 gap-y-2 py-3 pr-4 pl-6 md:grid-cols-[1fr_auto] md:items-center"
            style={{ ["--holder" as string]: STATUS_COLOR[a.status] ?? "var(--color-ink-soft)" }}
          >
            <div>
              <div className="flex flex-wrap items-baseline gap-x-3">
                <span className="font-strip text-2xl font-semibold">{a.tool_name}</span>
                <span className="text-ink-soft">{formatParams(a.params)}</span>
                <span className="text-sm text-ink-soft">#{a.id}</span>
              </div>
              {a.reason && <p className="mt-1">{a.reason}</p>}
              <p className="mt-1 text-sm text-ink-soft">
                Requested by {a.requested_by} {minutesAgo(a.created_at)} · needs {a.approver_role} or higher
                {a.decided_by && <> · decided by {a.decided_by}</>}
              </p>
              {a.result && a.status !== "pending" && <p className="mt-1 text-sm">Result: {a.result}</p>}
            </div>
            <div className="flex items-center gap-3">
              {canDecide(a) ? (
                <>
                  <Button tone="hold" disabled={busyId === a.id} onClick={() => decide(a, true)}>Approve and run</Button>
                  <Button tone="quiet" disabled={busyId === a.id} onClick={() => decide(a, false)}>Reject</Button>
                </>
              ) : (
                <Status value={a.status} />
              )}
            </div>
          </li>
        ))}
      </ol>
    </>
  );
}
