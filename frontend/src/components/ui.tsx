import type { ReactNode } from "react";

export const STATUS_COLOR: Record<string, string> = {
  healthy: "var(--color-healthy)",
  degraded: "var(--color-degraded)",
  down: "var(--color-down)",
  // tool and approval outcomes
  executed: "var(--color-healthy)",
  approved: "var(--color-healthy)",
  pending: "var(--color-hold)",
  pending_approval: "var(--color-hold)",
  executing: "var(--color-hold)",
  conflict: "var(--color-degraded)",
  invalid: "var(--color-degraded)",
  failed: "var(--color-down)",
  denied: "var(--color-down)",
  rejected: "var(--color-ink-soft)",
  cancelled: "var(--color-ink-soft)",
  unavailable: "var(--color-down)",
  unknown_tool: "var(--color-down)",
};

const LABEL: Record<string, string> = {
  pending_approval: "awaiting approval",
  unknown_tool: "unknown tool",
};

export function Status({ value }: { value: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm font-medium whitespace-nowrap">
      <span aria-hidden className="size-2.5 rounded-full" style={{ background: STATUS_COLOR[value] ?? "var(--color-ink-soft)" }} />
      {LABEL[value] ?? value}
    </span>
  );
}

/** Scaled from 0 to at least `floor`, so normal noise stays flat and only real spikes rise. */
export function Sparkline({ values, color, label, floor }: { values: number[]; color: string; label: string; floor: number }) {
  if (values.length < 2) return <span className="text-sm text-ink-soft">no data</span>;
  const w = 120, h = 28;
  const min = 0, max = Math.max(floor, ...values);
  const span = max - min;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - 2 - ((v - min) / span) * (h - 4)}`).join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={label} className="overflow-visible">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.75" strokeLinejoin="round" />
    </svg>
  );
}

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <h1 className="font-strip text-4xl font-bold tracking-tight">{title}</h1>
      {children}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <p role="alert" className="strip mb-4 py-2 pr-3 pl-5 text-sm" style={{ ["--holder" as string]: "var(--color-down)" }}>
      {message}
    </p>
  );
}

export function Button({
  children,
  tone = "ink",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "ink" | "hold" | "quiet" }) {
  const tones = {
    ink: "bg-ink text-strip hover:bg-ink-soft",
    hold: "bg-hold text-white hover:brightness-110",
    quiet: "bg-transparent text-ink border border-ink/30 hover:bg-strip",
  };
  return (
    <button
      {...props}
      className={`px-3.5 py-1.5 font-strip text-base font-semibold tracking-wide disabled:opacity-50 ${tones[tone]} ${props.className ?? ""}`}
    >
      {children}
    </button>
  );
}
