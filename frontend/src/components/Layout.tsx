import clsx from "clsx";
import {
  BookOpen, ClipboardCheck, FilePlus2, Files, LogOut, Menu, MessageSquareText, Palette, Settings, ShieldCheck, Users, X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Navigate, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Role } from "../api/types";
import { useMe, useResetSession } from "../hooks";
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
    { to: "/drafts/new", label: "New draft", icon: FilePlus2 },
    { to: "/queue", label: "Review queue", icon: ClipboardCheck },
    { to: "/admin/rules", label: "Rulebook", icon: BookOpen },
    { to: "/admin/facts", label: "Evidence", icon: ShieldCheck },
    { to: "/admin/voice", label: "Voice", icon: MessageSquareText },
    { to: "/admin/palette", label: "Palette", icon: Palette },
    { to: "/team", label: "Team", icon: Users },
  ],
};

export const HOME: Record<Role, string> = { creator: "/drafts", reviewer: "/queue", admin: "/drafts" };

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={clsx("shrink-0", className)}>
      <rect width="32" height="32" rx="7" fill="#0F172A" />
      <path d="M9 16.5l4.5 4.5L23 11.5" stroke="#fff" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2.5 text-[15px] font-semibold tracking-tight text-ink">
      <LogoMark className="h-7 w-7" /> Countersign
    </Link>
  );
}

function SideNav({ items, onNavigate }: { items: NavItem[]; onNavigate?: () => void }) {
  const link = ({ isActive }: { isActive: boolean }) => clsx(
    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors duration-150",
    isActive ? "bg-slate-100 font-medium text-ink" : "text-ink-soft hover:bg-slate-50 hover:text-ink");
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

const ROLE_LABEL: Record<Role, string> = { creator: "Creator", reviewer: "Reviewer", admin: "Admin" };

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
  if (!me) return <Navigate to={`/login?next=${encodeURIComponent(pathname)}`} replace />;
  const role = me.user.role;
  const allowed = !roles || roles.includes(role);
  const signOut = async () => { await api.post("/api/auth/logout"); await reset(); nav("/login"); };

  const panel = (
    <div className="flex h-full flex-col">
      <div className="flex h-16 shrink-0 items-center px-5"><Logo /></div>
      <div className="flex-1 overflow-y-auto px-3 py-2">
        <p className="truncate px-3 pb-2 text-[11px] font-medium uppercase tracking-wider text-ink-faint">{me.org.name}</p>
        <SideNav items={NAV[role]} onNavigate={() => setMenu(false)} />
      </div>
      <div className="border-t border-line p-4" style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}>
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-sm font-medium text-ink-soft">
            {me.user.name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase()}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{me.user.name}</p>
            <p className="truncate text-xs text-ink-faint">{ROLE_LABEL[role]} · {me.user.email}</p>
          </div>
          <button onClick={signOut} aria-label="Sign out" title="Sign out"
            className="rounded-md p-2 text-ink-faint hover:bg-slate-100 hover:text-ink"><LogOut className="h-4 w-4" /></button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-dvh lg:pl-64">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-line bg-white lg:block">{panel}</aside>

      {menu && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setMenu(false)} />
          <div className="absolute inset-y-0 left-0 w-[min(18rem,85vw)] bg-white shadow-pop">
            <button onClick={() => setMenu(false)} aria-label="Close menu"
              className="absolute right-3 top-4 rounded-md p-2 text-ink-soft hover:bg-slate-100"><X className="h-5 w-5" /></button>
            {panel}
          </div>
        </div>
      )}

      <header className="sticky top-0 z-20 border-b border-line bg-white/95 backdrop-blur lg:hidden" style={{ paddingTop: "env(safe-area-inset-top)" }}>
        <div className="flex h-14 items-center gap-3 px-4 sm:px-6">
          <button onClick={() => setMenu(true)} aria-label="Open menu" aria-expanded={menu}
            className="-ml-1.5 rounded-md p-2 text-ink-soft hover:bg-slate-100"><Menu className="h-5 w-5" /></button>
          <Logo />
          <span className="ml-auto rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-ink-soft">{ROLE_LABEL[role]}</span>
        </div>
      </header>

      <main className="px-4 py-6 sm:px-6 lg:px-10 lg:py-8" style={{ paddingBottom: "max(1.5rem, env(safe-area-inset-bottom))" }}>
        {allowed ? children : <p className="text-ink-soft">This page is for {roles!.join(" or ")} accounts.</p>}
      </main>
    </div>
  );
}
