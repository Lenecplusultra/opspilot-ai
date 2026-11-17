import { useEffect, useState } from "react";
import { formatParams, minutesAgo, type AuditEntry } from "../api";
import { useAuth } from "../auth";
import { ErrorNote, PageHeader, Status } from "../components/ui";

const CHANNELS = [
  { value: "", label: "All channels" },
  { value: "agent", label: "Copilot agent" },
  { value: "mcp", label: "MCP clients" },
  { value: "api", label: "Direct API" },
];

const OUTCOMES = ["", "executed", "pending_approval", "approved", "rejected", "denied", "failed", "conflict", "invalid"];

export default function Audit() {
  const { call } = useAuth();
  const [rows, setRows] = useState<AuditEntry[] | null>(null);
  const [channel, setChannel] = useState("");
  const [outcome, setOutcome] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const q = new URLSearchParams({ limit: "200" });
    if (channel) q.set("channel", channel);
    if (outcome) q.set("outcome", outcome);
    call<AuditEntry[]>(`/audit?${q}`).then(setRows).catch((e) => setError(e.message));
  }, [call, channel, outcome]);

  return (
    <>
      <PageHeader title="Audit log">
        <div className="flex flex-wrap gap-2">
          <select value={channel} onChange={(e) => setChannel(e.target.value)} className="border border-strip-edge bg-strip px-3 py-1.5" aria-label="Channel">
            {CHANNELS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
          <select value={outcome} onChange={(e) => setOutcome(e.target.value)} className="border border-strip-edge bg-strip px-3 py-1.5" aria-label="Outcome">
            {OUTCOMES.map((o) => <option key={o} value={o}>{o ? o.replace("_", " ") : "All outcomes"}</option>)}
          </select>
        </div>
      </PageHeader>
      <p className="mb-4 text-sm text-ink-soft">
        Append-only. The database rejects updates and deletes on this table, so entries cannot be edited after the fact.
      </p>
      {error && <ErrorNote message={error} />}
      {rows && rows.length === 0 && <p className="text-ink-soft">No entries match these filters.</p>}
      {rows && rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse bg-strip text-sm">
            <thead>
              <tr className="border-b border-strip-edge text-left font-strip text-base">
                <th className="px-3 py-2 font-semibold">When</th>
                <th className="px-3 py-2 font-semibold">Who</th>
                <th className="px-3 py-2 font-semibold">Via</th>
                <th className="px-3 py-2 font-semibold">Tool</th>
                <th className="px-3 py-2 font-semibold">Outcome</th>
                <th className="px-3 py-2 font-semibold">Detail</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-strip-edge/70 align-top">
                  <td className="px-3 py-2 whitespace-nowrap text-ink-soft" title={r.created_at}>{minutesAgo(r.created_at)}</td>
                  <td className="px-3 py-2">{r.user}<div className="text-ink-soft">{r.role}</div></td>
                  <td className="px-3 py-2">{r.channel}</td>
                  <td className="px-3 py-2">
                    <span className="font-strip text-base font-semibold">{r.tool_name}</span>
                    <div className="max-w-56 truncate text-ink-soft" title={formatParams(r.params)}>{formatParams(r.params)}</div>
                  </td>
                  <td className="px-3 py-2">
                    <Status value={r.outcome} />
                    {r.approval_id && <div className="text-ink-soft">request #{r.approval_id}</div>}
                  </td>
                  <td className="max-w-72 px-3 py-2 break-words text-ink-soft">{r.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
