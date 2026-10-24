import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { InviteInfo, Role } from "../api/types";
import { HOME, Logo } from "../components/Layout";
import { Button, ErrorNote, Spinner } from "../components/ui";
import { useMe, useResetSession } from "../hooks";

function AuthShell({ title, subtitle, children, footer }:
  { title: string; subtitle?: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-canvas" style={{ paddingTop: "env(safe-area-inset-top)" }}>
      <header className="px-4 py-5 sm:px-8"><Logo /></header>
      <main className="flex flex-1 items-start justify-center px-4 pb-16 pt-6 sm:items-center sm:pt-0">
        <div className="w-full max-w-[400px]">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {subtitle && <p className="mt-1.5 text-sm text-ink-soft">{subtitle}</p>}
          <div className="mt-6 rounded-xl border border-line bg-white p-5 shadow-card sm:p-6">{children}</div>
          {footer && <p className="mt-5 text-center text-sm text-ink-soft">{footer}</p>}
        </div>
      </main>
    </div>
  );
}

function Field({ label, hint, ...rest }: React.InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  return (
    <label className="block text-sm">
      <span className="font-medium">{label}</span>
      <input className="field" {...rest} />
      {hint && <span className="mt-1 block text-xs text-ink-faint">{hint}</span>}
    </label>
  );
}

function useSignedIn() {
  const nav = useNavigate();
  const reset = useResetSession();
  const [params] = useSearchParams();
  return async (role: Role) => {
    await reset();
    const next = params.get("next");
    nav(next && next.startsWith("/") && !next.startsWith("//") ? next : HOME[role], { replace: true });
  };
}

export function LoginPage() {
  const { data: me } = useMe();
  const done = useSignedIn();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (me) return <Navigate to={HOME[me.user.role]} replace />;
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ role: Role }>("/api/auth/login", { email: f.get("email"), password: f.get("password") });
      await done(r.role);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthShell title="Sign in" subtitle="Use the email your admin invited, or the one you signed up with."
      footer={<>New to Countersign? <Link to="/signup" className="font-medium text-ink underline underline-offset-2">Create a workspace</Link></>}>
      <form className="space-y-4" onSubmit={submit}>
        <Field label="Work email" name="email" type="email" autoComplete="email" required autoFocus />
        <Field label="Password" name="password" type="password" autoComplete="current-password" required />
        <ErrorNote error={error} />
        <Button type="submit" variant="primary" className="w-full" busy={busy}>Sign in</Button>
        <p className="text-xs text-ink-faint">Forgot your password? Ask your workspace admin for a reset link.</p>
      </form>
    </AuthShell>
  );
}

export function SignupPage() {
  const { data: me } = useMe();
  const done = useSignedIn();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (me) return <Navigate to={HOME[me.user.role]} replace />;
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ role: Role }>("/api/auth/signup", {
        name: f.get("name"), email: f.get("email"), password: f.get("password"), company: f.get("company"),
      });
      await done(r.role);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthShell title="Create a workspace" subtitle="You become the admin. Invite creators and reviewers from the Team page."
      footer={<>Already have an account? <Link to="/login" className="font-medium text-ink underline underline-offset-2">Sign in</Link></>}>
      <form className="space-y-4" onSubmit={submit}>
        <Field label="Company name" name="company" autoComplete="organization" required autoFocus maxLength={200} />
        <Field label="Your name" name="name" autoComplete="name" required maxLength={120} />
        <Field label="Work email" name="email" type="email" autoComplete="email" required />
        <Field label="Password" name="password" type="password" autoComplete="new-password" required minLength={8}
          hint="At least 8 characters." />
        <ErrorNote error={error} />
        <Button type="submit" variant="primary" className="w-full" busy={busy}>Create workspace</Button>
      </form>
    </AuthShell>
  );
}

const ROLE_TEXT: Record<Role, string> = {
  creator: "write drafts and send them for review", reviewer: "review and countersign drafts",
  admin: "manage the rulebook, evidence and team",
};

export function InvitePage() {
  const { token = "" } = useParams();
  const done = useSignedIn();
  const q = useQuery({ queryKey: ["invite", token], queryFn: () => api.get<InviteInfo>(`/api/invites/${token}`), retry: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (q.isLoading) return <AuthShell title="Checking your link"><Spinner /></AuthShell>;
  if (!q.data) {
    return (
      <AuthShell title="Link not valid" footer={<Link to="/login" className="font-medium text-ink underline">Go to sign in</Link>}>
        <ErrorNote error={q.error} />
      </AuthShell>
    );
  }
  const inv = q.data;
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    if (f.get("password") !== f.get("confirm")) {
      setError(new Error("The two passwords do not match"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ role: Role }>(`/api/invites/${token}/accept`, { password: f.get("password"), name: f.get("name") || null });
      await done(r.role);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  const reset = inv.kind === "reset";
  return (
    <AuthShell title={reset ? "Set a new password" : `Join ${inv.org_name}`}
      subtitle={reset ? <>For {inv.email}</> : <>You're invited as <b className="font-medium text-ink">{inv.role}</b>: you can {ROLE_TEXT[inv.role]}.</>}>
      <form className="space-y-4" onSubmit={submit}>
        <Field label="Email" value={inv.email} readOnly disabled />
        {!reset && <Field label="Your name" name="name" defaultValue={inv.name} autoComplete="name" required maxLength={120} />}
        <Field label={reset ? "New password" : "Password"} name="password" type="password" autoComplete="new-password"
          required minLength={8} hint="At least 8 characters." autoFocus />
        <Field label="Confirm password" name="confirm" type="password" autoComplete="new-password" required minLength={8} />
        <ErrorNote error={error} />
        <Button type="submit" variant="primary" className="w-full" busy={busy}>{reset ? "Save password" : "Join workspace"}</Button>
      </form>
    </AuthShell>
  );
}
