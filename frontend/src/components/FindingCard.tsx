import clsx from "clsx";
import { AlertTriangle, BadgeCheck, CircleSlash, Info, Scale } from "lucide-react";
import type { ClaimLabel, Finding } from "../api/types";
import { Badge, Button, LABEL_TONE, laneBadge } from "./ui";

const SEV_TONE = { blocking: "red", warning: "amber", advisory: "violet", info: "neutral" } as const;
const STATUS_TEXT: Record<string, string> = {
  accepted: "Fix applied (re-check to confirm)", edited: "Edited", dismissed: "Dismissed by creator",
  overridden: "Overridden by reviewer", resolved: "Resolved",
};

export interface CardActions {
  canAccept: boolean;
  canDismiss: boolean;
  canOverride: boolean;
  onAccept: () => void;
  onDismiss: () => void;
  onOverride: () => void;
  onReopen: () => void;
  busy: boolean;
}

export function FindingCard({ f, active, onSelect, actions, reasons }:
  { f: Finding; active: boolean; onSelect: () => void; actions: CardActions; reasons?: string[] }) {
  const b = laneBadge(f);
  const sug = f.suggestion;
  const closed = ["dismissed", "overridden", "resolved"].includes(f.status);
  const cited = f.evidence.filter((e) => e.role === "cited");
  const candidates = f.evidence.filter((e) => e.role === "candidate");
  return (
    <li
      id={`finding-${f.id}`}
      tabIndex={0}
      onClick={onSelect}
      onFocus={onSelect}
      aria-label={`${b.text}: ${f.message}`}
      className={clsx("cursor-pointer rounded-xl border bg-white p-3.5 text-sm shadow-card transition-colors duration-150",
        active ? "border-brand-500 ring-2 ring-brand-100" : "border-line hover:border-slate-300", closed && "opacity-70")}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <span className={`hl-badge hl-badge-${b.cls} !mx-0`}>{b.text}</span>
        <Badge tone={SEV_TONE[f.severity]}>{f.severity}</Badge>
        {f.source === "ai" && <Badge tone="neutral">AI</Badge>}
        {f.source === "rule" && <Badge tone="neutral">Rule</Badge>}
        {f.source === "pattern" && <Badge tone="amber">Pattern, needs human review</Badge>}
        {f.carried_over && <Badge tone="neutral">carried over</Badge>}
      </div>
      <p className="mt-2 font-medium">{f.message}</p>
      <p className="mt-1 break-words text-ink-soft">“{f.span.text.length > 140 ? f.span.text.slice(0, 140) + "…" : f.span.text}”</p>
      {f.explanation && <p className="mt-1.5 text-ink-soft">{f.explanation}</p>}

      {cited.map((e) => (
        <div key={e.fact_code} className="mt-2 rounded-lg bg-ink/[0.03] p-2.5">
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <b>{e.fact_code}</b>
            {e.verified && <span className="inline-flex items-center gap-0.5 text-leaf-700"><BadgeCheck className="h-3.5 w-3.5" /> quote verified</span>}
            {e.status !== "valid" && <Badge tone="amber">{e.status}{e.valid_to ? ` ${e.valid_to}` : ""}{e.superseded_by ? ` by ${e.superseded_by}` : ""}</Badge>}
          </div>
          {e.quote && <p className="mt-1">“{e.quote}”</p>}
          <p className="mt-1 text-xs text-ink-faint">{e.source_document}{e.source_locator ? `, ${e.source_locator}` : ""} · owner {e.owner}</p>
        </div>
      ))}
      {candidates.length > 0 && (
        <p className="mt-2 text-xs text-ink-faint">Facts to check: {candidates.map((c) => c.fact_code).join(", ")}</p>
      )}
      {f.regulatory_prompt && (
        <p className="mt-2 flex gap-1.5 text-xs text-ink-soft"><Scale className="mt-0.5 h-3.5 w-3.5 shrink-0" />{f.regulatory_prompt}</p>
      )}

      {sug?.replacement != null && !closed && f.status !== "accepted" && (
        <div className="mt-2.5 rounded-lg border border-leaf-100 bg-leaf-50 p-2.5">
          <p className="text-xs font-medium text-leaf-700">
            Suggested fix · {sug.kind === "deterministic" ? "rule-based" : "AI, re-checked"}
            {sug.recheck?.intent_score != null && ` · keeps intent ${sug.recheck.intent_score}/5`}
          </p>
          <p className="mt-1"><del className="text-ink-faint">{f.span.text}</del> → <ins className="no-underline font-medium">{sug.replacement || "(remove)"}</ins></p>
        </div>
      )}
      {sug?.replacement == null && sug?.approach && !closed && (
        <p className="mt-2 flex gap-1.5 rounded-lg bg-amber-50 p-2.5 text-xs text-amber-900"><Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />{sug.approach}</p>
      )}

      {f.status !== "open" && (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-ink-soft">
          {f.status === "dismissed" ? <CircleSlash className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
          {STATUS_TEXT[f.status] ?? f.status}{reasons?.length ? `: “${reasons[reasons.length - 1]}”` : ""}
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-1.5" onClick={(e) => e.stopPropagation()}>
        {actions.canAccept && sug?.replacement != null && f.status === "open" && (
          <Button variant="primary" className="px-2.5 py-1 text-xs" onClick={actions.onAccept} busy={actions.busy}>Accept fix</Button>
        )}
        {actions.canDismiss && f.status === "open" && f.severity !== "info" && (
          <Button className="px-2.5 py-1 text-xs" onClick={actions.onDismiss}>Dismiss…</Button>
        )}
        {actions.canOverride && ["open", "dismissed"].includes(f.status) && f.severity === "blocking" && (
          <Button className="px-2.5 py-1 text-xs" onClick={actions.onOverride}>Override…</Button>
        )}
        {(actions.canDismiss || actions.canOverride) && ["dismissed", "overridden"].includes(f.status) && (
          <Button variant="ghost" className="px-2.5 py-1 text-xs" onClick={actions.onReopen}>Reopen</Button>
        )}
      </div>
    </li>
  );
}

export function ClaimLabelBadge({ label }: { label: ClaimLabel | null }) {
  if (!label) return null;
  return <Badge tone={LABEL_TONE[label]}>{label}</Badge>;
}
