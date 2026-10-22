import clsx from "clsx";
import { Check, ChevronDown, ListChecks, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, NavLink, Navigate, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Role } from "../api/types";
import { CHECKLIST, useChecklist, useMe, useResetSession } from "../hooks";
import { Spinner } from "./ui";

const NAV: Record<Role, { to: string; label: string }[]> = {
  creator: [{ to: "/drafts", label: "My drafts" }, { to: "/drafts/new", label: "New draft" }],
  reviewer: [{ to: "/queue", label: "Review queue" }, { to: "/drafts", label: "All drafts" }],
  admin: [
    { to: "/drafts", label: "Drafts" }, { to: "/queue", label: "Queue" }, { to: "/admin/rules", label: "Rulebook" },
    { to: "/admin/facts", label: "Evidence" }, { to: "/admin/voice", label: "Voice" },
    { to: "/admin/palette", label: "Palette" },
  ],
};

export function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2 font-serif text-lg font-semibold">
      <img src="/favicon.svg" alt="" className="h-6 w-6" /> Countersign
    </Link>
  );
}

function RoleSwitcher({ role }: { role: Role }) {
  const [open, setOpen] = useState(false);
  const reset = useResetSession();
  const nav = useNavigate();
  const go = async (r: Role) => {
    setOpen(false);
    await api.post("/api/demo/switch-role", { role: r });
    await reset();
    nav(r === "reviewer" ? "/queue" : "/drafts");
  };
  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)} aria-haspopup="menu" aria-expanded={open}
        className="flex items-center gap-1 rounded-lg border border-ink/15 bg-white px-2.5 py-1.5 text-sm">
        Viewing as <b className="capitalize">{role}</b> <ChevronDown className="h-4 w-4" />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-40 mt-1 w-56 rounded-lg border border-ink/10 bg-white p-1 shadow-lg">
          {(["creator", "reviewer", "admin"] as Role[]).map((r) => (
            <button key={r} role="menuitem" onClick={() => go(r)}
              className="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm capitalize hover:bg-ink/5">
              {r} {r === role && <Check className="h-4 w-4 text-leaf-500" />}
            </button>
          ))}
          <p className="px-3 pb-2 pt-1 text-xs text-ink-faint">Demo only: same sandbox, different person.</p>
        </div>
      )}
    </div>
  );
}

function Checklist({ org }: { org: string }) {
  const done = useChecklist(org);
  const [hidden, setHidden] = useState(() => {
    try { return localStorage.getItem("cs-checklist-hidden") === "1"; } catch { return false; }
  });
  const hide = (v: boolean) => {
    setHidden(v);
    try { localStorage.setItem("cs-checklist-hidden", v ? "1" : "0"); } catch { /* ignore */ }
  };
  if (hidden) {
    return (
      <button onClick={() => hide(false)} className="fixed bottom-4 right-4 z-30 flex items-center gap-1.5 rounded-full bg-ink px-3 py-2 text-sm text-white shadow-lg">
        <ListChecks className="h-4 w-4" /> Tour {done.length}/{CHECKLIST.length}
      </button>
    );
  }
  // a slim step bar under the header: it guides without ever covering the page
  return (
    <div aria-label="Guided tour" className="border-b border-ink/10 bg-leaf-50">
      <div className="mx-auto no-scrollbar flex max-w-7xl items-center gap-3 overflow-x-auto px-4 py-2">
        <span className="shrink-0 text-xs font-semibold uppercase tracking-wide text-leaf-700">3-minute tour</span>
        <ol className="flex gap-1.5">
          {CHECKLIST.map((s, i) => {
            const ok = done.includes(s.key);
            const next = !ok && CHECKLIST.findIndex((c) => !done.includes(c.key)) === i;
            return (
              <li key={s.key} className={clsx("flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs",
                ok ? "text-ink-faint line-through" : next ? "bg-white font-medium text-ink shadow-sm" : "text-ink-soft")}>
                <span className={clsx("flex h-4 w-4 items-center justify-center rounded-full border text-[10px] no-underline",
                  ok ? "border-leaf-500 bg-leaf-500 text-white" : "border-ink/30")}>{ok ? <Check className="h-3 w-3" /> : i + 1}</span>
                {s.label}
              </li>
            );
          })}
        </ol>
        <button onClick={() => hide(true)} aria-label="Hide tour" className="ml-auto shrink-0 rounded p-1 text-ink-soft hover:bg-ink/5"><X className="h-4 w-4" /></button>
      </div>
    </div>
  );
}

export function AppLayout({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { data: me, isLoading } = useMe();
  const reset = useResetSession();
  const nav = useNavigate();
  if (isLoading) return <div className="p-8"><Spinner /></div>;
  if (!me) return <Navigate to="/" replace />;
  const role = me.user.role;
  const allowed = !roles || roles.includes(role);
  const signOut = async () => { await api.post("/api/auth/logout"); await reset(); nav("/"); };
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-ink/10 bg-paper/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <Logo />
          <nav className="flex flex-wrap gap-1" aria-label="Main">
            {NAV[role].map((n) => (
              <NavLink key={n.to} to={n.to} end
                className={({ isActive }) => clsx("rounded-md px-2.5 py-1.5 text-sm",
                  isActive ? "bg-ink/[0.07] font-medium" : "text-ink-soft hover:text-ink")}>
                {n.label}
              </NavLink>
            ))}
            <NavLink to="/settings" className={({ isActive }) => clsx("rounded-md px-2.5 py-1.5 text-sm",
              isActive ? "bg-ink/[0.07] font-medium" : "text-ink-soft hover:text-ink")}>Settings</NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span className="hidden text-ink-soft md:inline">{me.user.name} · {me.org.name}{me.org.is_sandbox && " (sandbox)"}</span>
            {me.org.is_sandbox ? <RoleSwitcher role={role} /> : <span className="capitalize">{role}</span>}
            <button onClick={signOut} className="text-ink-soft underline-offset-2 hover:underline">Leave</button>
          </div>
        </div>
        {me.org.is_sandbox && <Checklist org={me.org.slug} />}
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        {allowed ? children : <p className="text-ink-soft">This page is for {roles!.join(" or ")} users. Use the role switcher above.</p>}
      </main>
    </div>
  );
}
