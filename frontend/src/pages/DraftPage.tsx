import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, Send } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { Comment, DraftDetail, Finding, Review } from "../api/types";
import { CHANNEL_LABEL } from "../api/types";
import { ClaimLabelBadge, FindingCard } from "../components/FindingCard";
import { Button, Card, Empty, ErrorNote, ReasonModal, Spinner, StatusBadge, timeAgo } from "../components/ui";
import { FindingsEditor, type EditorHandle } from "../editor/FindingsEditor";
import { HistoryPanel } from "./HistoryPanel";

type FindingWithDecisions = Finding & { decisions?: { action: string; reason: string | null }[] };
const EDITABLE = ["draft", "checking", "checked", "changes_requested"];
const LANE_LABEL: Record<string, string> = { rules: "Rules", claims: "Claims", voice: "Voice", fixes: "Fixes" };

function LaneChips({ review }: { review?: Review }) {
  const ls = review?.job?.lane_status ?? {};
  return (
    <div className="flex flex-wrap gap-1.5" aria-live="polite">
      {["rules", "claims", "voice", "fixes"].map((lane) => {
        const s = ls[lane] ?? "queued";
        return (
          <span key={lane} className={clsx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs",
            s === "done" ? "bg-leaf-50 text-leaf-700 ring-1 ring-inset ring-leaf-100" : s === "degraded" || s === "unavailable" ? "bg-amber-50 text-amber-900 ring-1 ring-inset ring-amber-200" : "bg-slate-100 text-ink-soft")}>
            {s === "done" ? <CheckCircle2 className="h-3 w-3" /> : s === "running" ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
            {LANE_LABEL[lane]}{s === "done" ? "" : s === "degraded" ? " · pattern fallback" : s === "unavailable" ? " · unavailable" : ` · ${s}`}
          </span>
        );
      })}
    </div>
  );
}

function group(findings: FindingWithDecisions[]) {
  return [
    { title: "Blocking", items: findings.filter((f) => f.severity === "blocking") },
    { title: "Warnings", items: findings.filter((f) => f.severity === "warning") },
    { title: "Supported claims", items: findings.filter((f) => f.severity === "info") },
    { title: "Advisory (voice)", items: findings.filter((f) => f.severity === "advisory") },
  ].filter((g) => g.items.length);
}

export default function DraftPage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "history" ? "history" : "review";
  const qc = useQueryClient();
  const editorRef = useRef<EditorHandle>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [modal, setModal] = useState<null | { kind: "dismiss" | "override"; finding: Finding } | { kind: "reject" | "request_changes" }>(null);
  const [claimsReviewed, setClaimsReviewed] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  const draftQ = useQuery({ queryKey: ["draft", id], queryFn: () => api.get<DraftDetail>(`/api/drafts/${id}`) });
  const draft = draftQ.data;
  const versionId = draft?.current_version_id;
  const reviewQ = useQuery({
    queryKey: ["review", versionId],
    queryFn: () => api.get<Review>(`/api/versions/${versionId}/review`),
    enabled: !!versionId,
    refetchInterval: (q) => (q.state.data?.job && ["done", "failed"].includes(q.state.data.job.status) ? false : 1000),
  });
  const review = reviewQ.data;
  const findings = (review?.findings ?? []) as FindingWithDecisions[];
  const jobDone = review?.job?.status === "done";

  useEffect(() => {
    if (jobDone) qc.invalidateQueries({ queryKey: ["draft", id] });
  }, [jobDone, id, qc]);
  useEffect(() => { setDirty(false); setActiveId(null); setClaimsReviewed(false); }, [versionId]);

  const canEdit = !!draft?.can.edit && EDITABLE.includes(draft.status);
  const isReviewer = !!draft?.can.review && draft.status === "in_review";
  const refresh = useCallback(() => {
    qc.invalidateQueries({ queryKey: ["review", versionId] });
    qc.invalidateQueries({ queryKey: ["draft", id] });
    qc.invalidateQueries({ queryKey: ["history", id] });
  }, [qc, versionId, id]);

  const decide = useMutation({
    mutationFn: ({ fid, action, reason }: { fid: string; action: string; reason?: string }) =>
      api.post(`/api/findings/${fid}/decision`, { action, reason }),
    onSuccess: refresh,
    onMutate: () => setActionError(null),
    onError: setActionError,
  });
  const recheck = useMutation({
    mutationFn: () => api.post<{ version_id: string }>(`/api/drafts/${id}/versions`, { text: editorRef.current!.getText() }),
    onSuccess: refresh,
    onMutate: () => setActionError(null),
    onError: setActionError,
  });
  const send = useMutation({
    mutationFn: () => api.post(`/api/drafts/${id}/send-for-review`),
    onSuccess: refresh,
    onMutate: () => setActionError(null),
    onError: setActionError,
  });
  const verdict = useMutation({
    mutationFn: (body: { decision: string; reason?: string; claims_reviewed?: boolean }) =>
      api.post(`/api/drafts/${id}/decision`, body),
    onSuccess: () => { setModal(null); refresh(); },
    onMutate: () => setActionError(null),
    onError: (e) => { setModal(null); setActionError(e); },
  });
  const retry = useMutation({
    mutationFn: () => api.post(`/api/versions/${versionId}/retry-ai`),
    onSuccess: refresh,
    onMutate: () => setActionError(null),
    onError: setActionError,
  });

  const accept = (f: Finding) => {
    const rep = f.suggestion?.replacement;
    if (rep == null) return;
    if (editorRef.current?.applyFix(f.id, rep)) {
      setDirty(true);
      decide.mutate({ fid: f.id, action: "accept" });
    } else {
      setActionError(new Error("That text has changed since the check. Re-check to get fresh suggestions."));
    }
  };

  const select = useCallback((fid: string) => {
    setActiveId(fid);
    document.getElementById(`finding-${fid}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, []);

  // keyboard: arrow keys move between findings, A accepts
  const listRef = useRef<HTMLOListElement>(null);
  const onListKey = (e: React.KeyboardEvent) => {
    const ids = findings.map((f) => f.id);
    const i = activeId ? ids.indexOf(activeId) : -1;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const next = ids[Math.max(0, Math.min(ids.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
      if (next) { setActiveId(next); document.getElementById(`finding-${next}`)?.focus(); editorRef.current?.focusFinding(next); }
    } else if (e.key === "Enter" && activeId) {
      editorRef.current?.focusFinding(activeId);
    } else if ((e.key === "a" || e.key === "A") && activeId && canEdit) {
      const f = findings.find((x) => x.id === activeId);
      if (f) accept(f);
    }
  };

  const blockingOpen = findings.filter((f) => f.severity === "blocking" && ["open", "accepted", "edited"].includes(f.status)).length;
  const claims = findings.filter((f) => f.lane === "claims");
  const groups = useMemo(() => group(findings), [findings]);

  if (draftQ.isLoading) return <Spinner />;
  if (!draft) return <ErrorNote error={draftQ.error ?? new Error("Draft not found")} />;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="page-title break-words">{draft.title}</h1>
            <StatusBadge status={draft.status} />
          </div>
          <p className="mt-1 text-sm text-ink-soft">
            {CHANNEL_LABEL[draft.channel]} · v{draft.current_version_no} · by {draft.author?.name} · purpose: {draft.purpose}
          </p>
        </div>
        <div role="tablist" className="flex gap-1 rounded-lg bg-slate-100 p-1">
          {(["review", "history"] as const).map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setParams(t === "review" ? {} : { tab: t })}
              className={clsx("rounded-md px-3 py-1.5 text-sm capitalize", tab === t ? "bg-white font-medium shadow-sm" : "text-ink-soft")}>{t}</button>
          ))}
        </div>
      </div>

      {tab === "history" ? <HistoryPanel draft={draft} /> : (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_400px] 2xl:grid-cols-[minmax(0,1fr)_460px]">
          <div className="min-w-0 space-y-4">
            <Card className="overflow-hidden">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
                <LaneChips review={review} />
                {review?.job?.timings?.rules_ms != null && (
                  <span className="text-xs text-ink-faint">rules {String(review.job.timings.rules_ms)} ms
                    {review.job.timings.total_ms ? ` · all lanes ${(Number(review.job.timings.total_ms) / 1000).toFixed(1)} s` : ""}</span>
                )}
              </div>
              {review?.job?.ai_degraded && jobDone && (
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-900" role="status">
                  <span className="flex items-center gap-1.5"><AlertTriangle className="h-4 w-4" />
                    AI checks unavailable: claims were flagged by pattern and need human review.</span>
                  {canEdit && <Button className="py-1 text-xs" onClick={() => retry.mutate()} busy={retry.isPending}><RefreshCw className="h-3.5 w-3.5" /> Retry AI checks</Button>}
                </div>
              )}
              {review ? (
                <FindingsEditor ref={editorRef} versionId={review.version.id} text={review.version.text} findings={findings}
                  editable={canEdit && jobDone} activeId={activeId} onSelect={select} onDirtyChange={setDirty} />
              ) : <div className="p-5"><Spinner /></div>}
              {canEdit && (
                <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-4 py-3">
                  <p className="text-sm text-ink-soft">
                    {!jobDone ? "Checks running… you can edit when they finish." : dirty ? "You have unsaved edits. Re-check to save them as a new version."
                      : blockingOpen ? `${blockingOpen} blocking finding${blockingOpen > 1 ? "s" : ""} to fix or dismiss.` : "No open blocking findings."}
                  </p>
                  <div className="flex w-full gap-2 sm:w-auto [&>button]:flex-1 sm:[&>button]:flex-none">
                    <Button onClick={() => recheck.mutate()} disabled={!dirty || !jobDone} busy={recheck.isPending}>
                      <RefreshCw className="h-4 w-4" /> Re-check
                    </Button>
                    <Button variant="primary" onClick={() => send.mutate()} disabled={dirty || !jobDone || blockingOpen > 0 || draft.status !== "checked"} busy={send.isPending}>
                      <Send className="h-4 w-4" /> Send for countersign
                    </Button>
                  </div>
                </div>
              )}
            </Card>
            {!isReviewer && <ErrorNote error={actionError} />}

            {isReviewer && (
              <Card className="p-4">
                <h2 className="section-title">Countersign</h2>
                {claims.length > 0 && (
                  <div className="mt-3 overflow-x-auto">
                    <p className="mb-2 text-sm font-medium">Claims ledger</p>
                    <table className="w-full text-sm">
                      <thead className="text-left text-xs uppercase tracking-wide text-ink-faint">
                        <tr><th className="py-1.5 pr-3">Claim</th><th className="pr-3">Label</th><th className="pr-3">Fact</th><th className="pr-3">Owner</th><th className="pr-3">Valid to</th><th>Status</th></tr>
                      </thead>
                      <tbody>
                        {claims.map((c) => {
                          const e = c.evidence.find((x) => x.role === "cited");
                          return (
                            <tr key={c.id} className="cursor-pointer border-t border-ink/5 hover:bg-ink/[0.02]" onClick={() => select(c.id)}>
                              <td className="py-2 pr-3">“{c.span.text}”</td>
                              <td className="pr-3"><ClaimLabelBadge label={c.claim?.label ?? null} /></td>
                              <td className="pr-3">{e?.fact_code ?? "—"}</td>
                              <td className="pr-3">{e?.owner ?? "—"}</td>
                              <td className="pr-3">{e?.valid_to ?? (e ? "open-ended" : "—")}</td>
                              <td className="capitalize">{c.status}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    <label className="mt-3 flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={claimsReviewed} onChange={(e) => setClaimsReviewed(e.target.checked)} className="h-4 w-4 accent-brand-500" />
                      I have reviewed all {claims.length} claims
                    </label>
                  </div>
                )}
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button variant="primary" busy={verdict.isPending}
                    onClick={() => verdict.mutate({ decision: "approve", claims_reviewed: claimsReviewed })}>Approve</Button>
                  <Button onClick={() => setModal({ kind: "request_changes" })}>Request changes…</Button>
                  <Button variant="danger" onClick={() => setModal({ kind: "reject" })}>Reject…</Button>
                </div>
                <div className="mt-3"><ErrorNote error={actionError} /></div>
                {draft.current_version_no > 1 && (
                  <p className="mt-3 text-sm text-ink-soft">
                    Compare with v{draft.current_version_no - 1} in <button className="underline" onClick={() => setParams({ tab: "history" })}>History</button>.
                  </p>
                )}
              </Card>
            )}
            <Comments draftId={draft.id} />
          </div>

          <aside aria-label="Findings" className="min-w-0 xl:sticky xl:top-14 xl:self-start">
            <div className="mb-2 flex items-baseline justify-between">
              <h2 className="section-title">Findings</h2>
              <span className="hidden text-xs text-ink-faint sm:inline">↑/↓ to move · Enter to show · A to accept</span>
            </div>
            {!review || (!jobDone && findings.length === 0) ? <Spinner label="Checking your draft…" /> : null}
            {jobDone && findings.length === 0 && <Empty title="All clear">No rule, claim or voice issues found.</Empty>}
            <ol ref={listRef} onKeyDown={onListKey} className="space-y-4 xl:max-h-[calc(100dvh-8rem)] xl:overflow-y-auto xl:pr-1">
              {groups.map((g) => (
                <li key={g.title}>
                  <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-faint">{g.title} · {g.items.length}</p>
                  <ol className="space-y-2">
                    {g.items.map((f) => (
                      <FindingCard key={f.id} f={f} active={f.id === activeId}
                        reasons={f.decisions?.map((d) => d.reason).filter((r): r is string => !!r)}
                        onSelect={() => { setActiveId(f.id); editorRef.current?.focusFinding(f.id); }}
                        actions={{
                          canAccept: canEdit && jobDone, canDismiss: canEdit && jobDone, canOverride: isReviewer,
                          busy: decide.isPending,
                          onAccept: () => accept(f),
                          onDismiss: () => f.severity === "blocking" ? setModal({ kind: "dismiss", finding: f }) : decide.mutate({ fid: f.id, action: "dismiss" }),
                          onOverride: () => setModal({ kind: "override", finding: f }),
                          onReopen: () => decide.mutate({ fid: f.id, action: "reopen" }),
                        }} />
                    ))}
                  </ol>
                </li>
              ))}
            </ol>
          </aside>
        </div>
      )}

      <ReasonModal open={modal?.kind === "dismiss" || modal?.kind === "override"}
        title={modal?.kind === "override" ? "Override blocking finding" : "Dismiss blocking finding"}
        hint={modal?.kind === "override" ? "Why is this acceptable? Your reason is stored in the audit log." : "Why should this stay as written? A reviewer must agree before approval."}
        confirm={modal?.kind === "override" ? "Override" : "Dismiss"} busy={decide.isPending}
        onClose={() => setModal(null)}
        onSubmit={(reason) => {
          if (modal && "finding" in modal) decide.mutate({ fid: modal.finding.id, action: modal.kind, reason }, { onSettled: () => setModal(null) });
        }} />
      <ReasonModal open={modal?.kind === "reject" || modal?.kind === "request_changes"}
        title={modal?.kind === "reject" ? "Reject draft" : "Request changes"}
        hint="Tell the creator what to change. They will see this on the draft."
        confirm={modal?.kind === "reject" ? "Reject" : "Request changes"} busy={verdict.isPending}
        onClose={() => setModal(null)}
        onSubmit={(reason) => modal && verdict.mutate({ decision: modal.kind, reason })} />
    </div>
  );
}

function Comments({ draftId }: { draftId: string }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["comments", draftId], queryFn: () => api.get<Comment[]>(`/api/drafts/${draftId}/comments`) });
  const [body, setBody] = useState("");
  const add = useMutation({
    mutationFn: () => api.post(`/api/drafts/${draftId}/comments`, { body }),
    onSuccess: () => { setBody(""); qc.invalidateQueries({ queryKey: ["comments", draftId] }); },
  });
  return (
    <Card className="p-4">
      <h2 className="section-title">Comments</h2>
      <ul className="mt-2 space-y-2">
        {q.data?.length === 0 && <li className="text-sm text-ink-faint">No comments yet.</li>}
        {q.data?.map((c) => (
          <li key={c.id} className="rounded-lg bg-ink/[0.03] px-3 py-2 text-sm">
            <p className="text-xs text-ink-faint"><b className="text-ink">{c.author?.name}</b> ({c.author?.role}) · v{c.version_no} · {timeAgo(c.created_at)}</p>
            <p className="mt-0.5 whitespace-pre-wrap">{c.body}</p>
          </li>
        ))}
      </ul>
      <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (body.trim()) add.mutate(); }}>
        <label className="sr-only" htmlFor="comment">Add a comment</label>
        <input id="comment" value={body} onChange={(e) => setBody(e.target.value)} placeholder="Add a comment…"
          className="field mt-0 min-w-0 flex-1" />
        <Button type="submit" busy={add.isPending} disabled={!body.trim()}>Post</Button>
      </form>
      <ErrorNote error={add.error} />
    </Card>
  );
}

