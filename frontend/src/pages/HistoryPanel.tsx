import { useQuery } from "@tanstack/react-query";
import { Download, FileText, ShieldAlert, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { DraftDetail, History } from "../api/types";
import { Badge, Card, ErrorNote, Spinner } from "../components/ui";

interface Diff { ops: { op: "eq" | "ins" | "del"; text: string }[] }

const fmt = (iso: string) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

export function HistoryPanel({ draft }: { draft: DraftDetail }) {
  const q = useQuery({ queryKey: ["history", draft.id], queryFn: () => api.get<History>(`/api/drafts/${draft.id}/history`) });
  const n = draft.current_version_no;
  const [from, setFrom] = useState(Math.max(1, n - 1));
  const [to, setTo] = useState(n);
  useEffect(() => { setFrom(Math.max(1, n - 1)); setTo(n); }, [n]);
  const diff = useQuery({
    queryKey: ["diff", draft.id, from, to],
    queryFn: () => api.get<Diff>(`/api/drafts/${draft.id}/diff?from=${from}&to=${to}`),
    enabled: n > 0,
  });
  if (q.isLoading) return <Spinner />;
  if (!q.data) return <ErrorNote error={q.error} />;
  const h = q.data;
  const versionOptions = h.versions.map((v) => <option key={v.version_no} value={v.version_no}>v{v.version_no}</option>);

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <div className="min-w-0 space-y-5">
        <Card className="p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="section-title">Compare versions</h2>
            <div className="flex items-center gap-2 text-sm">
              <label className="sr-only" htmlFor="from">From version</label>
              <select id="from" value={from} onChange={(e) => setFrom(+e.target.value)} className="rounded border border-line bg-white px-2 py-1">{versionOptions}</select>
              →
              <label className="sr-only" htmlFor="to">To version</label>
              <select id="to" value={to} onChange={(e) => setTo(+e.target.value)} className="rounded border border-line bg-white px-2 py-1">{versionOptions}</select>
            </div>
          </div>
          <p className="mt-3 whitespace-pre-wrap rounded-lg bg-ink/[0.03] p-3 text-[15px] leading-7">
            {diff.data?.ops.map((o, i) => o.op === "eq" ? <span key={i}>{o.text}</span>
              : o.op === "ins" ? <ins key={i} className="bg-leaf-100 no-underline" title="added">{o.text}</ins>
                : <del key={i} className="bg-red-100 text-red-900" title="removed">{o.text}</del>)}
          </p>
          <p className="mt-2 text-xs text-ink-faint">Green = added, red strikethrough = removed.</p>
        </Card>

        <Card className="p-4">
          <h2 className="section-title">Versions</h2>
          <ol className="mt-2 space-y-2 text-sm">
            {h.versions.map((v) => (
              <li key={v.id} className="flex flex-wrap justify-between gap-2 border-b border-ink/5 pb-2 last:border-0">
                <span><b>v{v.version_no}</b> by {v.author?.name ?? "?"} · {v.source_type}</span>
                <span className="text-ink-faint">rulebook v{v.rulebook_version} · facts v{v.facts_version} · {fmt(v.created_at)}</span>
              </li>
            ))}
          </ol>
        </Card>

        <Card className="p-4">
          <h2 className="section-title">Decisions</h2>
          {h.decisions.length === 0 && <p className="mt-2 text-sm text-ink-faint">No workflow decisions yet.</p>}
          <ol className="mt-2 space-y-2 text-sm">
            {h.decisions.map((d, i) => (
              <li key={i}>
                <Badge tone={d.decision === "approved" ? "green" : d.decision === "submitted" ? "blue" : "red"}>{d.decision.replace("_", " ")}</Badge>{" "}
                <b>{d.actor?.name}</b> ({d.actor?.role}) on v{d.version_no} · {fmt(d.created_at)}
                {d.reason && <p className="mt-0.5 text-ink-soft">“{d.reason}”</p>}
                {d.claims_reviewed && <p className="text-xs text-ink-faint">Confirmed all claims reviewed</p>}
              </li>
            ))}
          </ol>
          {h.finding_decisions.length > 0 && (
            <>
              <p className="mt-4 text-sm font-medium">Finding decisions</p>
              <ol className="mt-1 space-y-1.5 text-sm">
                {h.finding_decisions.map((d, i) => (
                  <li key={i} className="text-ink-soft">
                    <b className="text-ink">{d.actor?.name}</b> {d.action} <b className="text-ink">{d.finding.code}</b> “{d.finding.span.slice(0, 60)}” on v{d.version_no}
                    {d.reason && <>: “{d.reason}”</>}
                  </li>
                ))}
              </ol>
            </>
          )}
          {draft.status === "approved" && (
            <div className="mt-4 flex flex-wrap gap-2">
              <a href={`/api/drafts/${draft.id}/export.csv`} className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-1.5 text-sm hover:bg-ink/[0.03]">
                <Download className="h-4 w-4" /> Export CSV</a>
              <a href={`/api/drafts/${draft.id}/record`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-1.5 text-sm hover:bg-ink/[0.03]">
                <FileText className="h-4 w-4" /> Printable review record</a>
            </div>
          )}
        </Card>
      </div>

      <Card className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="section-title">Audit log</h2>
          {h.chain.ok ? (
            <Badge tone="green"><ShieldCheck className="h-3.5 w-3.5" /> Hash chain verified ({h.chain.events} events)</Badge>
          ) : (
            <Badge tone="red"><ShieldAlert className="h-3.5 w-3.5" /> Chain broken at event {h.chain.broken_at}</Badge>
          )}
        </div>
        <p className="mt-1 text-xs text-ink-faint">Append-only: the database rejects edits and deletes. Each event's hash covers the previous one.</p>
        <ol className="mt-3 space-y-2 text-sm">
          {h.audit.map((e) => (
            <li key={e.id} className="rounded-lg border border-ink/5 px-3 py-2">
              <div className="flex flex-wrap justify-between gap-2">
                <span><code className="text-xs">{e.action}</code> {e.actor ? <>by <b>{e.actor.name}</b></> : <span className="text-ink-faint">by system</span>}</span>
                <span className="text-xs text-ink-faint">{fmt(e.created_at)}</span>
              </div>
              <p className="mt-0.5 truncate font-mono text-[11px] text-ink-faint" title={e.hash}>#{e.id} {e.hash.slice(0, 16)}… ← {e.prev_hash.slice(0, 8)}…</p>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
