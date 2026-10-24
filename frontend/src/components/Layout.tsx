import clsx from "clsx";
import {
  BookOpen, Check, ChevronDown, ClipboardCheck, FilePlus2, Files, ListChecks, LogOut, Menu, MessageSquareText,
  Palette, Settings, ShieldCheck, X, type LucideIcon,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Navigate, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Role } from "../api/types";
import { CHECKLIST, useChecklist, useMe, useResetSession } from "../hooks";
import { Spinner } from "./ui";

type NavItem = { to: string; label: string; icon: LucideIcon };
const NAV: Record<Role, NavItem[]> = {
  creator: [
    { to: "/drafts", label: "My drafts", icon: Files },
    { to: "/drafts/new", label: "New draft", icon: FilePlus2 },
  ],
  reviewer: [
    { to: "/queue", label: "Review queue", icon: ClipboardCheck },
    { to: "/drafts", label: "All drafts", icon: Files },
  ],
  admin: [
    { to: "/drafts", label: "Drafts", icon: Files },
    { to: "/queue", label: "Review queue", icon: ClipboardCheck },
    { to: "/admin/rules", label: "Rulebook", icon: BookOpen },
    { to: "/admin/facts", label: "Evidence", icon: ShieldCheck },
    { to: "/admin/voice", label: "Voice", icon: MessageSquareText },
    { to: "/admin/palette", label: "Palette", icon: Palette },
  ],
};

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={clsx("shrink-0", className)}>
      <rect width="32" height="32" rx="8" fill="#1D4ED8" />
      <path d="M9 16.5l4.5 4.5L23 11.5" stroke="#fff" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Logo({ light }: { light?: boolean }) {
  return (
    <Link to="/" className={clsx("flex items-center gap-2.5 text-[15px] font-semibold tracking-tight", light ? "text-white" : "text-ink")}>
      <LogoMark className="h-7 w-7" /> Countersign
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
        className="flex w-full items-center justify-between gap-2 rounded-lg border border-line bg-white px-3 py-2 text-sm shadow-sm hover:bg-slate-50">
        <span className="text-ink-soft">Role <b className="ml-1 font-medium capitalize text-ink">{role}</b></span>
        <ChevronDown className="h-4 w-4 text-ink-faint" />
      </button>
      {open && (
        <div role="menu" className="absolute bottom-full left-0 right-0 z-40 mb-1 rounded-lg border border-line bg-white p-1 shadow-pop">
          {(["creator", "reviewer", "admin"] as Role[]).map((r) => (
            <button key={r} role="menuitem" onClick={() => go(r)}
              className="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm capitalize hover:bg-slate-100">
              {r} {r === role && <Check className="h-4 w-4 text-brand-500" />}
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
      <button onClick={() => hide(false)}
        className="fixed bottom-4 right-4 z-30 flex items-center gap-1.5 rounded-full bg-ink px-3.5 py-2 text-sm text-white shadow-pop"
        style={{ marginBottom: "env(safe-area-inset-bottom)" }}>
        <ListChecks className="h-4 w-4" /> Guided tour {done.length}/{CHECKLIST.length}
      </button>
    );
  }
  // a slim step bar under the top bar: it guides without covering the page
  return (
    <div aria-label="Guided tour" className="flex items-center border-b border-line bg-white pr-2 sm:pr-4 lg:pr-6">
      <div className="no-scrollbar flex min-w-0 flex-1 items-center gap-3 overflow-x-auto py-2 pl-4 pr-2 sm:pl-6 lg:pl-8">
        <span className="shrink-0 text-xs font-medium text-ink-faint">Guided tour</span>
        <ol className="flex gap-1.5">
          {CHECKLIST.map((s, i) => {
            const ok = done.includes(s.key);
            const next = !ok && CHECKLIST.findIndex((c) => !done.includes(c.key)) === i;
            return (
              <li key={s.key} className={clsx("flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs",
                ok ? "text-ink-faint" : next ? "bg-brand-50 font-medium text-brand-700 ring-1 ring-inset ring-brand-100" : "text-ink-soft")}>
                <span className={clsx("flex h-4 w-4 items-center justify-center rounded-full border text-[10px]",
                  ok ? "border-leaf-500 bg-leaf-500 text-white" : next ? "border-brand-500" : "border-slate-300")}>
                  {ok ? <Check className="h-3 w-3" /> : i + 1}</span>
                {s.label}
              </li>
            );
          })}
        </ol>
      </div>
      <button onClick={() => hide(true)} aria-label="Hide tour"
        className="shrink-0 rounded-md border-l border-line p-1.5 pl-2 text-ink-faint hover:bg-slate-100 hover:text-ink">
        <X className="h-4 w-4" /></button>
    </div>
  );
}

function SideNav({ items, onNavigate }: { items: NavItem[]; onNavigate?: () => void }) {
  const link = ({ isActive }: { isActive: boolean }) => clsx(
    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors duration-150",
    isActive ? "bg-brand-50 font-medium text-brand-700" : "text-ink-soft hover:bg-slate-100 hover:text-ink");
  return (
    <nav className="space-y-0.5" aria-label="Main">
      {items.map((n) => (
        <NavLink key={n.to} to={n.to} end onClick={onNavigate} className={link}>
          <n.icon className="h-[18px] w-[18px] shrink-0" aria-hidden /> {n.label}
        </NavLink>
      ))}
      <NavLink to="/settings" onClick={onNavigate} className={link}>
        <Settings className="h-[18px] w-[18px] shrink-0" aria-hidden /> Settings
      </NavLink>
    </nav>
  );
}

export function AppLayout({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { data: me, isLoading } = useMe();
  const reset = useResetSession();
  const nav = useNavigate();
  const { pathname } = useLocation();
  const [menu, setMenu] = useState(false);
  useEffect(() => setMenu(false), [pathname]);
  useEffect(() => {
    if (!menu) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenu(false);
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = ""; };
  }, [menu]);
  if (isLoading) return <div className="grid min-h-dvh place-items-center"><Spinner /></div>;
  if (!me) return <Navigate to="/" replace />;
  const role = me.user.role;
  const allowed = !roles || roles.includes(role);
  const signOut = async () => { await api.post("/api/auth/logout"); await reset(); nav("/"); };

  const panel = (
    <div className="flex h-full flex-col">
      <div className="flex h-16 shrink-0 items-center px-5"><Logo /></div>
      <div className="flex-1 overflow-y-auto px-3 py-2">
        <p className="px-3 pb-2 text-[11px] font-medium uppercase tracking-wider text-ink-faint">Workspace</p>
        <SideNav items={NAV[role]} onNavigate={() => setMenu(false)} />
      </div>
      <div className="space-y-3 border-t border-line p-4" style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{me.user.name}</p>
          <p className="truncate text-xs text-ink-faint">{me.org.name}{me.org.is_sandbox && " · sandbox"}</p>
        </div>
        {me.org.is_sandbox ? <RoleSwitcher role={role} /> : <p className="text-sm capitalize text-ink-soft">{role}</p>}
        <button onClick={signOut} className="flex items-center gap-2 text-sm text-ink-soft hover:text-ink">
          <LogOut className="h-4 w-4" /> Leave workspace</button>
      </div>
    </div>
  );

  return (
    <div className="min-h-dvh lg:pl-64">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-line bg-white lg:block">{panel}</aside>

      {menu && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px]" onClick={() => setMenu(false)} />
          <div className="absolute inset-y-0 left-0 w-[min(18rem,85vw)] bg-white shadow-pop">
            <button onClick={() => setMenu(false)} aria-label="Close menu"
              className="absolute right-3 top-4 rounded-md p-2 text-ink-soft hover:bg-slate-100"><X className="h-5 w-5" /></button>
            {panel}
          </div>
        </div>
      )}

      <header className="sticky top-0 z-20 border-b border-line bg-white/90 backdrop-blur" style={{ paddingTop: "env(safe-area-inset-top)" }}>
        <div className="flex h-14 items-center gap-3 px-4 sm:px-6 lg:hidden">
          <button onClick={() => setMenu(true)} aria-label="Open menu" aria-expanded={menu}
            className="-ml-1.5 rounded-md p-2 text-ink-soft hover:bg-slate-100"><Menu className="h-5 w-5" /></button>
          <Logo />
          <span className="ml-auto rounded-md bg-slate-100 px-2 py-1 text-xs font-medium capitalize text-ink-soft">{role}</span>
        </div>
        {me.org.is_sandbox && <Checklist org={me.org.slug} />}
      </header>

      <main className="px-4 py-6 sm:px-6 lg:px-8 lg:py-8" style={{ paddingBottom: "max(1.5rem, env(safe-area-inset-bottom))" }}>
        {allowed ? children : (
          <p className="text-ink-soft">This page is for {roles!.join(" or ")} users. Switch role from the menu.</p>
        )}
      </main>
    </div>
  );
}
