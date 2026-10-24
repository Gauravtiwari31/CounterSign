import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, KeyRound, UserPlus, UserX } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { Role, Team, TeamInvite } from "../api/types";
import { Badge, Button, Card, ErrorNote, Modal, Spinner } from "../components/ui";

const ROLES: { value: Role; label: string; text: string }[] = [
  { value: "creator", label: "Creator", text: "Writes drafts and sends them for review" },
  { value: "reviewer", label: "Reviewer", text: "Reviews and countersigns drafts" },
  { value: "admin", label: "Admin", text: "Manages rulebook, evidence and team; can also review" },
];
const fmt = (iso: string) => new Date(iso).toLocaleDateString([], { day: "numeric", month: "short" });

function LinkBox({ title, token, onClose }: { title: string; token: string; onClose: () => void }) {
  const url = `${window.location.origin}/invite/${token}`;
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(url); setCopied(true); } catch { /* select the text instead */ }
  };
  return (
    <Modal open title={title} onClose={onClose}>
      <p className="text-sm text-ink-soft">Send this link to the person by email, chat or any channel you trust.
        It works once and expires in 7 days. It is shown only now.</p>
      <div className="mt-3 flex gap-2">
        <input readOnly value={url} onFocus={(e) => e.currentTarget.select()} className="field mt-0 min-w-0 flex-1 font-mono text-xs" aria-label="Invite link" />
        <Button onClick={copy}>{copied ? <><Check className="h-4 w-4" /> Copied</> : <><Copy className="h-4 w-4" /> Copy</>}</Button>
      </div>
      <div className="mt-4 flex justify-end"><Button variant="primary" onClick={onClose}>Done</Button></div>
    </Modal>
  );
}

export function TeamPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["team"], queryFn: () => api.get<Team>("/api/team") });
  const [inviting, setInviting] = useState(false);
  const [link, setLink] = useState<{ title: string; token: string } | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["team"] });

  const invite = useMutation({
    mutationFn: (body: { email: string; name: string; role: Role }) =>
      api.post<{ invite: TeamInvite; token: string }>("/api/team/invites", body),
    onSuccess: (r) => { setInviting(false); setLink({ title: `Invite link for ${r.invite.name}`, token: r.token }); refresh(); },
  });
  const changeRole = useMutation({
    mutationFn: ({ id, role }: { id: string; role: Role }) => api.put(`/api/team/users/${id}/role`, { role }),
    onSuccess: refresh,
  });
  const remove = useMutation({ mutationFn: (id: string) => api.del(`/api/team/users/${id}`), onSuccess: refresh });
  const resetLink = useMutation({
    mutationFn: (u: { id: string; name: string }) => api.post<{ token: string }>(`/api/team/users/${u.id}/reset-link`),
    onSuccess: (r, u) => setLink({ title: `Password link for ${u.name}`, token: r.token }),
  });
  const revoke = useMutation({ mutationFn: (id: string) => api.del(`/api/team/invites/${id}`), onSuccess: refresh });
  const resend = useMutation({
    mutationFn: (i: TeamInvite) => api.post<{ invite: TeamInvite; token: string }>("/api/team/invites",
      { email: i.email, name: i.name, role: i.role }),
    onSuccess: (r) => { setLink({ title: `New invite link for ${r.invite.name}`, token: r.token }); refresh(); },
  });

  const submitInvite = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    invite.mutate({ email: String(f.get("email")), name: String(f.get("name")), role: f.get("role") as Role });
  };
  const error = changeRole.error ?? remove.error ?? resetLink.error ?? revoke.error ?? resend.error;
  const active = q.data?.users.filter((u) => u.active) ?? [];
  const removed = q.data?.users.filter((u) => !u.active) ?? [];

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="page-title">Team</h1>
          <p className="mt-1 text-sm text-ink-soft">Invite people and choose what each person can do. A draft's author can never countersign it.</p>
        </div>
        <Button variant="primary" onClick={() => { invite.reset(); setInviting(true); }}><UserPlus className="h-4 w-4" /> Invite person</Button>
      </div>
      {q.isLoading && <Spinner />}
      <ErrorNote error={q.error ?? error} />

      {q.data && (
        <div className="space-y-6">
          <Card className="divide-y divide-line">
            {active.map((u) => (
              <div key={u.id} className="flex flex-wrap items-center gap-3 px-4 py-3.5 sm:px-5">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{u.name} {u.is_you && <span className="text-sm font-normal text-ink-faint">(you)</span>}</p>
                  <p className="truncate text-sm text-ink-faint">{u.email}{!u.has_password && " · no password set"}</p>
                </div>
                <label className="sr-only" htmlFor={`role-${u.id}`}>Role for {u.name}</label>
                <select id={`role-${u.id}`} value={u.role} disabled={changeRole.isPending}
                  onChange={(e) => changeRole.mutate({ id: u.id, role: e.target.value as Role })}
                  className="field mt-0 w-auto py-1.5">
                  {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
                <div className="flex gap-1">
                  <Button variant="ghost" className="px-2.5" title="Create a password link" aria-label={`Password link for ${u.name}`}
                    onClick={() => resetLink.mutate({ id: u.id, name: u.name })}><KeyRound className="h-4 w-4" /></Button>
                  {!u.is_you && (
                    <Button variant="ghost" className="px-2.5 text-red-700 hover:bg-red-50 hover:text-red-800" title="Remove from workspace"
                      aria-label={`Remove ${u.name}`} onClick={() => confirm(`Remove ${u.name}? They are signed out at once. Their drafts and decisions stay in the history.`) && remove.mutate(u.id)}>
                      <UserX className="h-4 w-4" /></Button>
                  )}
                </div>
              </div>
            ))}
          </Card>

          {q.data.invites.length > 0 && (
            <section>
              <h2 className="section-title mb-2">Pending invites</h2>
              <Card className="divide-y divide-line">
                {q.data.invites.map((i) => (
                  <div key={i.id} className="flex flex-wrap items-center gap-3 px-4 py-3 sm:px-5">
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{i.name} <span className="font-normal text-ink-faint">· {i.email}</span></p>
                      <p className="text-sm text-ink-faint">{ROLES.find((r) => r.value === i.role)?.label} · {i.expired ? "expired" : `expires ${fmt(i.expires_at)}`}</p>
                    </div>
                    {i.expired && <Badge tone="amber">Expired</Badge>}
                    <Button className="py-1.5" onClick={() => resend.mutate(i)} busy={resend.isPending && resend.variables?.id === i.id}>New link</Button>
                    <Button variant="ghost" className="py-1.5" onClick={() => revoke.mutate(i.id)}>Revoke</Button>
                  </div>
                ))}
              </Card>
            </section>
          )}

          {removed.length > 0 && (
            <p className="text-sm text-ink-faint">Removed: {removed.map((u) => u.name).join(", ")}</p>
          )}
        </div>
      )}

      <Modal open={inviting} title="Invite a person" onClose={() => setInviting(false)}>
        <form className="space-y-4 text-sm" onSubmit={submitInvite}>
          <label className="block"><span className="font-medium">Name</span><input name="name" required maxLength={120} className="field" /></label>
          <label className="block"><span className="font-medium">Work email</span><input name="email" type="email" required className="field" /></label>
          <fieldset>
            <legend className="font-medium">Role</legend>
            <div className="mt-2 space-y-2">
              {ROLES.map((r, i) => (
                <label key={r.value} className="flex cursor-pointer items-start gap-3 rounded-lg border border-line p-3 has-[:checked]:border-ink has-[:checked]:bg-slate-50">
                  <input type="radio" name="role" value={r.value} defaultChecked={i === 0} className="mt-0.5 accent-ink" />
                  <span><span className="font-medium">{r.label}</span><span className="block text-ink-soft">{r.text}</span></span>
                </label>
              ))}
            </div>
          </fieldset>
          <ErrorNote error={invite.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setInviting(false)}>Cancel</Button>
            <Button type="submit" variant="primary" busy={invite.isPending}>Create invite link</Button>
          </div>
        </form>
      </Modal>
      {link && <LinkBox title={link.title} token={link.token} onClose={() => setLink(null)} />}
    </div>
  );
}
