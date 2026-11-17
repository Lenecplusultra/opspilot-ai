import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth";

const LINKS = [
  { to: "/", label: "Board", hint: "Fleet health" },
  { to: "/copilot", label: "Copilot", hint: "Ask the agent" },
  { to: "/approvals", label: "Approvals", hint: "Requests to decide" },
  { to: "/audit", label: "Audit log", hint: "Every action", minRole: "sre" as const },
];

export default function Layout() {
  const { session, logout, atLeast } = useAuth();
  return (
    <div className="min-h-screen md:grid md:grid-cols-[220px_1fr]">
      <aside className="flex flex-col gap-6 bg-ink px-4 py-5 text-strip md:min-h-screen">
        <div className="font-strip text-2xl font-bold tracking-tight">OpsPilot</div>
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto md:flex-col">
          {LINKS.filter((l) => !l.minRole || atLeast(l.minRole)).map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.to === "/"}
              className={({ isActive }) =>
                `block shrink-0 border-l-4 px-3 py-2 ${isActive ? "border-strip bg-white/10" : "border-transparent hover:bg-white/5"}`
              }
            >
              <span className="block font-strip text-lg font-semibold">{l.label}</span>
              <span className="hidden text-xs text-strip/60 md:block">{l.hint}</span>
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto hidden text-sm md:block">
          <div className="truncate">{session?.email}</div>
          <div className="text-strip/60">Role: {session?.role}</div>
          <button onClick={logout} className="mt-2 underline underline-offset-4 hover:text-white">
            Sign out
          </button>
        </div>
      </aside>
      <main className="mx-auto w-full max-w-6xl px-4 py-6 md:px-8 md:py-8">
        <Outlet />
      </main>
    </div>
  );
}
