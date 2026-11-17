import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { Overview, Scenario, ServiceHealth } from "../api";
import { useAuth } from "../auth";
import { Button, ErrorNote, PageHeader, Sparkline, Status, STATUS_COLOR } from "../components/ui";

function fmt(v: number | undefined, unit = "") {
  if (v === undefined) return "–";
  return `${v >= 100 ? Math.round(v).toLocaleString() : v.toFixed(1)}${unit}`;
}

function ServiceStrip({ s, index }: { s: ServiceHealth; index: number }) {
  const holder = STATUS_COLOR[s.status];
  return (
    <li
      className="strip strip-in grid grid-cols-2 gap-x-6 gap-y-3 py-3 pr-4 pl-6 md:grid-cols-[minmax(170px,1.3fr)_110px_1fr_1fr_110px] md:items-center"
      style={{ ["--holder" as string]: holder, animationDelay: `${index * 60}ms` }}
    >
      <div className="col-span-2 md:col-span-1">
        <div className="font-strip text-2xl leading-tight font-semibold">{s.service}</div>
        <div className="text-sm text-ink-soft">
          v{s.version}
          {s.depends_on.length > 0 && <> · depends on {s.depends_on.join(", ")}</>}
        </div>
      </div>
      <Status value={s.status} />
      <div className="order-last col-span-2 flex items-center gap-3 md:order-none md:col-span-1">
        <Sparkline values={s.series.error_rate} color={holder} label={`${s.service} error rate, last hour`} floor={5} />
        <div className="text-sm">
          <div className="font-semibold">{fmt(s.metrics.error_rate, "%")}</div>
          <div className="text-ink-soft">errors</div>
        </div>
      </div>
      <div className="order-last col-span-2 flex items-center gap-3 md:order-none md:col-span-1">
        <Sparkline values={s.series.latency_p95_ms} color={holder} label={`${s.service} p95 latency, last hour`} floor={1000} />
        <div className="text-sm">
          <div className="font-semibold">{fmt(s.metrics.latency_p95_ms, " ms")}</div>
          <div className="text-ink-soft">p95</div>
        </div>
      </div>
      <div className="text-sm">
        <div className={s.dlq_dead ? "font-semibold text-down" : "font-semibold"}>{s.dlq_dead} dead</div>
        {s.metrics.queue_depth !== undefined && <div className="text-ink-soft">queue {fmt(s.metrics.queue_depth)}</div>}
      </div>
    </li>
  );
}

export default function Board() {
  const { call, atLeast } = useAuth();
  const [data, setData] = useState<Overview | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [chosen, setChosen] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(() => {
    call<Overview>("/system/overview").then(setData).catch((e) => setError(e.message));
  }, [call]);

  useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    call<Scenario[]>("/system/scenarios").then((s) => {
      setScenarios(s);
      setChosen(s[0]?.name ?? "");
    }).catch(() => {});
  }, [call]);

  async function replayScenario() {
    setNotice("");
    try {
      const r = await call<{ events_replayed: number }>(`/system/scenarios/${chosen}/replay`, { method: "POST" });
      setNotice(`Replayed ${r.events_replayed} events from ${chosen}. Pending approvals were cancelled.`);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Replay failed");
    }
  }

  const troubled = data?.services.filter((s) => s.status !== "healthy") ?? [];
  // Like a strip board: services that need attention go to the top.
  const RANK: Record<string, number> = { down: 0, degraded: 1, healthy: 2 };
  const ordered = [...(data?.services ?? [])].sort((a, b) => RANK[a.status] - RANK[b.status] || a.service.localeCompare(b.service));

  return (
    <>
      <PageHeader title="Fleet board">
        {data && (
          <p className="text-ink-soft">
            {troubled.length === 0 ? "All services healthy" : troubled.length === 1 ? "1 service needs attention" : `${troubled.length} services need attention`}
            {" · "}
            {data.dlq_dead_total} dead-lettered
            {" · "}
            <Link to="/approvals" className="underline underline-offset-4">
              {data.pending_approvals} awaiting approval
            </Link>
          </p>
        )}
      </PageHeader>
      {error && <ErrorNote message={error} />}
      {!data && !error && <p className="text-ink-soft">Loading the board…</p>}
      {data && (
        <ol className="flex flex-col gap-2" aria-label="Services, most urgent first">
          {ordered.map((s, i) => (
            <ServiceStrip key={s.service} s={s} index={i} />
          ))}
        </ol>
      )}
      {troubled.length > 0 && (
        <p className="mt-6 text-ink-soft">
          Ask the <Link to="/copilot" className="text-ink underline underline-offset-4">Copilot</Link> what is wrong with{" "}
          {troubled.map((s) => s.service).join(" and ")}.
        </p>
      )}

      {atLeast("admin") && scenarios.length > 0 && (
        <section className="mt-12 max-w-2xl border-t border-board-deep pt-6">
          <h2 className="font-strip text-2xl font-semibold">Replay an incident</h2>
          <p className="mt-1 text-sm text-ink-soft">
            Rebuilds the simulated fleet from a recorded event log. The eval harness uses the same replays.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <select value={chosen} onChange={(e) => setChosen(e.target.value)} className="border border-strip-edge bg-strip px-3 py-1.5" aria-label="Scenario">
              {scenarios.map((s) => (
                <option key={s.name} value={s.name}>{s.name}</option>
              ))}
            </select>
            <Button onClick={replayScenario}>Replay scenario</Button>
          </div>
          <p className="mt-2 text-sm">{scenarios.find((s) => s.name === chosen)?.description}</p>
          {notice && <p role="status" className="mt-2 text-sm font-medium text-healthy">{notice}</p>}
        </section>
      )}
    </>
  );
}
