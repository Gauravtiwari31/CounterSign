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
        <h1 className="font-serif text-2xl font-semibold">{mine ? "My drafts" : "Drafts"}</h1>
        {me?.user.role !== "reviewer" && (
          <Link to="/drafts/new" className="inline-flex items-center gap-1.5 rounded-lg bg-leaf-500 px-3.5 py-2 text-sm font-medium text-white hover:bg-leaf-600">
            <Plus className="h-4 w-4" /> New draft
          </Link>
        )}
      </div>
      <div className="mb-4 flex flex-wrap gap-1.5" role="tablist" aria-label="Filter by status">
        {FILTERS.map((f) => (
          <button key={f} role="tab" aria-selected={filter === f} onClick={() => setFilter(f)}
            className={clsx("rounded-full border px-3 py-1 text-sm",
              filter === f ? "border-ink bg-ink text-white" : "border-ink/15 bg-white text-ink-soft hover:text-ink")}>
            {f === "all" ? "All" : STATUS_LABEL[f]}
          </button>
        ))}
      </div>
      {q.isLoading ? <Spinner /> : <ErrorNote error={q.error} />}
      {q.data && q.data.length === 0 && (
        <Empty title="No drafts here yet">
          {mine ? <>Start with <Link className="text-leaf-600 underline" to="/drafts/new?sample=1">the Round 1 example</Link>.</> : "Try another filter."}
        </Empty>
      )}
      {q.data && q.data.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-ink/10 bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-ink/10 text-left text-xs uppercase tracking-wide text-ink-faint">
              <tr><th className="px-4 py-2.5">Draft</th><th className="px-4">Status</th><th className="px-4">Blocking</th>
                <th className="px-4">Claims</th><th className="px-4">Channel</th><th className="px-4">Updated</th></tr>
            </thead>
            <tbody>
              {q.data.map((d) => (
                <tr key={d.id} className="border-b border-ink/5 last:border-0 hover:bg-ink/[0.02]">
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
      <h1 className="mb-1 font-serif text-2xl font-semibold">Review queue</h1>
      <p className="mb-5 text-sm text-ink-soft">Drafts waiting for your countersign, oldest first.</p>
      {q.isLoading ? <Spinner /> : <ErrorNote error={q.error} />}
      {q.data && q.data.length === 0 && <Empty title="Nothing waiting">New submissions from creators appear here.</Empty>}
      {q.data && q.data.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-ink/10 bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-ink/10 text-left text-xs uppercase tracking-wide text-ink-faint">
              <tr><th className="px-4 py-2.5">Draft</th><th className="px-4">Creator</th><th className="px-4">Channel</th>
                <th className="px-4">Blocking open</th><th className="px-4">Claims</th><th className="px-4">Dismissed by creator</th><th className="px-4">Waiting</th></tr>
            </thead>
            <tbody>
              {[...q.data].reverse().map((d) => (
                <tr key={d.id} className="border-b border-ink/5 last:border-0 hover:bg-ink/[0.02]">
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
