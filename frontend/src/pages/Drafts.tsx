import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { DraftStatus, DraftSummary } from "../api/types";
import { CHANNEL_LABEL, STATUS_LABEL } from "../api/types";
import { Badge, Empty, ErrorNote, Spinner, StatusBadge, timeAgo } from "../components/ui";
import { useMe } from "../hooks";

const FILTERS: (DraftStatus | "all")[] = ["all", "checked", "in_review", "changes_requested", "approved", "rejected"];

export function DraftsPage() {
  const { data: me } = useMe();
  const [filter, setFilter] = useState<DraftStatus | "all">("all");
  const mine = me?.user.role === "creator";
  const q = useQuery({
    queryKey: ["drafts", filter, mine],
    queryFn: () => api.get<DraftSummary[]>(`/api/drafts?mine=${mine}${filter === "all" ? "" : `&status=${filter}`}`),
  });
  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h1 className="page-title">{mine ? "My drafts" : "Drafts"}</h1>
        {me?.user.role !== "reviewer" && (
          <Link to="/drafts/new" className="inline-flex min-h-[36px] items-center gap-1.5 rounded-lg bg-ink px-3.5 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-slate-800">
            <Plus className="h-4 w-4" /> New draft
          </Link>
        )}
      </div>
      <div className="no-scrollbar -mx-4 mb-4 flex gap-1.5 overflow-x-auto px-4 sm:mx-0 sm:flex-wrap sm:px-0" role="tablist" aria-label="Filter by status">
        {FILTERS.map((f) => (
          <button key={f} role="tab" aria-selected={filter === f} onClick={() => setFilter(f)}
            className={clsx("shrink-0 rounded-full border px-3 py-1.5 text-sm transition-colors",
              filter === f ? "border-ink bg-ink text-white" : "border-line bg-white text-ink-soft hover:border-slate-300 hover:text-ink")}>
            {f === "all" ? "All" : STATUS_LABEL[f]}
          </button>
        ))}
      </div>
      {q.isLoading ? <Spinner /> : <ErrorNote error={q.error} />}
      {q.data && q.data.length === 0 && (
        <Empty title="No drafts here yet">
          {mine ? <>Paste a caption, email or product copy in <Link className="text-brand-600 underline" to="/drafts/new">New draft</Link>.</> : "Try another filter."}
        </Empty>
      )}
      {q.data && q.data.length > 0 && (
        <ul className="space-y-2 md:hidden">
          {q.data.map((d) => (
            <li key={d.id}>
              <Link to={`/drafts/${d.id}`} className="block rounded-xl border border-line bg-white p-4 shadow-card active:bg-slate-50">
                <div className="flex items-start justify-between gap-3">
                  <p className="min-w-0 break-words font-medium">{d.title}</p>
                  <StatusBadge status={d.status} />
                </div>
                <p className="mt-1 text-xs text-ink-faint">v{d.current_version_no} · {d.author?.name} · {CHANNEL_LABEL[d.channel]} · {timeAgo(d.updated_at)}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {d.counts.blocking_open > 0 && <Badge tone="red">{d.counts.blocking_open} blocking</Badge>}
                  <Badge>{d.counts.claims} claims</Badge>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {q.data && q.data.length > 0 && (
        <div className="hidden table-wrap md:block">
          <table className="w-full text-sm">
            <thead className="table-head">
              <tr><th className="px-4 py-2.5">Draft</th><th className="px-4">Status</th><th className="px-4">Blocking</th>
                <th className="px-4">Claims</th><th className="px-4">Channel</th><th className="px-4">Updated</th></tr>
            </thead>
            <tbody>
              {q.data.map((d) => (
                <tr key={d.id} className="border-b border-slate-100 transition-colors last:border-0 hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link to={`/drafts/${d.id}`} className="font-medium hover:underline">{d.title}</Link>
                    <p className="text-xs text-ink-faint">v{d.current_version_no} · {d.author?.name}</p>
                  </td>
                  <td className="px-4"><StatusBadge status={d.status} /></td>
                  <td className="px-4">{d.counts.blocking_open > 0 ? <Badge tone="red">{d.counts.blocking_open} open</Badge> : <span className="text-ink-faint">0</span>}</td>
                  <td className="px-4">{d.counts.claims}</td>
                  <td className="px-4">{CHANNEL_LABEL[d.channel]}</td>
                  <td className="px-4 text-ink-soft">{timeAgo(d.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function QueuePage() {
  const q = useQuery({
    queryKey: ["queue"],
    queryFn: () => api.get<DraftSummary[]>("/api/drafts?status=in_review"),
    refetchInterval: 10_000,
  });
  return (
    <div>
      <h1 className="mb-1 page-title">Review queue</h1>
      <p className="mb-5 text-sm text-ink-soft">Drafts waiting for your countersign, oldest first.</p>
      {q.isLoading ? <Spinner /> : <ErrorNote error={q.error} />}
      {q.data && q.data.length === 0 && <Empty title="Nothing waiting">New submissions from creators appear here.</Empty>}
      {q.data && q.data.length > 0 && (
        <ul className="space-y-2 md:hidden">
          {[...q.data].reverse().map((d) => (
            <li key={d.id}>
              <Link to={`/drafts/${d.id}`} className="block rounded-xl border border-line bg-white p-4 shadow-card active:bg-slate-50">
                <p className="break-words font-medium">{d.title}</p>
                <p className="mt-1 text-xs text-ink-faint">{d.author?.name} · {CHANNEL_LABEL[d.channel]} · waiting {timeAgo(d.updated_at)}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <Badge tone={d.counts.blocking_open > 0 ? "red" : "neutral"}>{d.counts.blocking_open} blocking open</Badge>
                  <Badge>{d.counts.claims} claims</Badge>
                  {d.counts.dismissed > 0 && <Badge tone="amber">{d.counts.dismissed} dismissed</Badge>}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {q.data && q.data.length > 0 && (
        <div className="hidden table-wrap md:block">
          <table className="w-full text-sm">
            <thead className="table-head">
              <tr><th className="px-4 py-2.5">Draft</th><th className="px-4">Creator</th><th className="px-4">Channel</th>
                <th className="px-4">Blocking open</th><th className="px-4">Claims</th><th className="px-4">Dismissed by creator</th><th className="px-4">Waiting</th></tr>
            </thead>
            <tbody>
              {[...q.data].reverse().map((d) => (
                <tr key={d.id} className="border-b border-slate-100 transition-colors last:border-0 hover:bg-slate-50">
                  <td className="px-4 py-3"><Link to={`/drafts/${d.id}`} className="font-medium hover:underline">{d.title}</Link></td>
                  <td className="px-4">{d.author?.name}</td>
                  <td className="px-4">{CHANNEL_LABEL[d.channel]}</td>
                  <td className="px-4">{d.counts.blocking_open}</td>
                  <td className="px-4">{d.counts.claims}</td>
                  <td className="px-4">{d.counts.dismissed > 0 ? <Badge tone="amber">{d.counts.dismissed}</Badge> : 0}</td>
                  <td className="px-4 text-ink-soft">{timeAgo(d.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
