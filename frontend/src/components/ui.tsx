import clsx from "clsx";
import { Loader2, X } from "lucide-react";
import { useEffect, useRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import type { ClaimLabel, DraftStatus, Finding } from "../api/types";
import { STATUS_LABEL } from "../api/types";

type Variant = "primary" | "secondary" | "ghost" | "danger";

export function Button({ variant = "secondary", busy, className, children, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; busy?: boolean }) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || busy}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition",
        "disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-leaf-500 text-white hover:bg-leaf-600",
        variant === "secondary" && "border border-ink/15 bg-white text-ink hover:bg-ink/[0.03]",
        variant === "ghost" && "text-ink-soft hover:bg-ink/5",
        variant === "danger" && "border border-red-200 bg-white text-red-700 hover:bg-red-50",
        className,
      )}
    >
      {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={clsx("rounded-xl border border-ink/10 bg-white", className)}>{children}</div>;
}

export function Badge({ tone = "neutral", children, className }:
  { tone?: "neutral" | "green" | "red" | "amber" | "blue" | "violet"; children: ReactNode; className?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-1 whitespace-nowrap rounded-md px-1.5 py-0.5 text-xs font-medium", {
      "bg-ink/[0.06] text-ink-soft": tone === "neutral",
      "bg-leaf-100 text-leaf-700": tone === "green",
      "bg-red-100 text-red-800": tone === "red",
      "bg-amber-100 text-amber-900": tone === "amber",
      "bg-blue-100 text-blue-800": tone === "blue",
      "bg-violet-100 text-violet-800": tone === "violet",
    }, className)}>{children}</span>
  );
}

const STATUS_TONE: Record<DraftStatus, "neutral" | "green" | "red" | "amber" | "blue"> = {
  draft: "neutral", checking: "blue", checked: "neutral", in_review: "amber", changes_requested: "red",
  approved: "green", rejected: "red",
};

export function StatusBadge({ status }: { status: DraftStatus }) {
  return <Badge tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Badge>;
}

export const LABEL_TONE: Record<ClaimLabel, "green" | "red" | "amber"> = {
  SUPPORTED: "green", UNSUPPORTED: "red", CONTRADICTED: "red", EXPIRED: "amber",
};

/** The text badge every finding carries: lane conveyed by words, not only colour. */
export function laneBadge(f: Finding): { text: string; cls: string } {
  const closed = ["dismissed", "overridden", "resolved"].includes(f.status);
  if (f.lane === "rules") return { text: `RULES · ${f.rule?.code ?? ""}`, cls: closed ? "closed" : "rules" };
  if (f.lane === "voice") return { text: `VOICE · ${f.criterion_code ?? "ADVISORY"}`, cls: closed ? "closed" : "voice" };
  const label = f.claim?.label ?? "CLAIM";
  return { text: `CLAIM · ${label}`, cls: closed ? "closed" : label === "SUPPORTED" ? "claims-ok" : "claims" };
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-ink-soft" role="status">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> {label ?? "Loading…"}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">{(error as Error).message}</p>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-ink/20 px-6 py-10 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-1 text-sm text-ink-soft">{children}</div>}
    </div>
  );
}

export function Modal({ open, title, onClose, children }:
  { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const field = ref.current?.querySelector<HTMLElement>("textarea, input, select")
      ?? ref.current?.querySelector<HTMLElement>("form button, button");
    field?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); prev?.focus(); };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4" onMouseDown={onClose}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={title}
        className="w-full max-w-lg rounded-xl bg-white p-5 shadow-xl" onMouseDown={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-serif text-lg font-semibold">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="rounded p-1 text-ink-soft hover:bg-ink/5"><X className="h-4 w-4" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function ReasonModal({ open, title, hint, confirm, onClose, onSubmit, busy, required = true }:
  { open: boolean; title: string; hint: string; confirm: string; onClose: () => void;
    onSubmit: (reason: string) => void; busy?: boolean; required?: boolean }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  return (
    <Modal open={open} title={title} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); onSubmit(ref.current?.value.trim() ?? ""); }}>
        <label className="text-sm text-ink-soft" htmlFor="reason">{hint}</label>
        <textarea id="reason" ref={ref} required={required} rows={3}
          className="mt-1.5 w-full rounded-lg border border-ink/15 p-2.5 text-sm" />
        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" busy={busy}>{confirm}</Button>
        </div>
      </form>
    </Modal>
  );
}

export function timeAgo(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
}
