export type Role = "viewer" | "engineer" | "sre" | "admin";
export const ROLE_RANK: Record<Role, number> = { viewer: 1, engineer: 2, sre: 3, admin: 4 };

export interface Session {
  token: string;
  email: string;
  role: Role;
}

export interface ServiceHealth {
  service: string;
  status: "healthy" | "degraded" | "down";
  version: string;
  depends_on: string[];
  restart_count: number;
  dlq_dead: number;
  metrics: Partial<Record<"latency_p95_ms" | "error_rate" | "cpu_percent" | "queue_depth", number>>;
  series: { error_rate: number[]; latency_p95_ms: number[] };
}

export interface Overview {
  services: ServiceHealth[];
  dlq_dead_total: number;
  pending_approvals: number;
}

export interface Approval {
  id: number;
  tool_name: string;
  params: Record<string, unknown>;
  reason: string;
  status: string;
  requested_by: string;
  decided_by: string | null;
  approver_role: Role;
  result: string | null;
  created_at: string;
  decided_at: string | null;
}

export interface AuditEntry {
  id: number;
  user: string;
  role: Role;
  channel: "api" | "agent" | "mcp";
  tool_name: string;
  params: Record<string, unknown>;
  outcome: string;
  detail: string;
  approval_id: number | null;
  created_at: string;
}

export interface AgentStep {
  tool: string;
  args: Record<string, unknown>;
  status: string;
  message: string;
  approval_id: number | null;
}

export interface ChatReply {
  reply: string;
  stop_reason: string;
  steps: AgentStep[];
  approval_ids: number[];
}

export interface Scenario {
  name: string;
  description: string;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const STORAGE_KEY = "opspilot.session";

export function loadSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function saveSession(s: Session | null) {
  try {
    if (s) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(s));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable: session lives in memory only */
  }
}

export async function api<T>(path: string, token: string | null, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail : body.message ?? `Request failed (${res.status})`;
    throw new ApiError(res.status, detail);
  }
  return body as T;
}

export function minutesAgo(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  return h < 24 ? `${h} h ago` : `${Math.round(h / 24)} d ago`;
}

export function formatParams(p: Record<string, unknown>): string {
  return Object.entries(p)
    .filter(([k, v]) => k !== "reason" && v !== null && v !== "")
    .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join(", ");
}
