import { ArrowRight, BookCheck, FileSearch, History, MessageSquareQuote, ShieldCheck, UserCheck } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Role } from "../api/types";
import { Logo } from "../components/Layout";
import { Button, ErrorNote } from "../components/ui";
import { useMe, useResetSession } from "../hooks";

const LANES = [
  { icon: BookCheck, title: "Rules", tag: "Deterministic · instant",
    text: "Your rulebook applied word by word: product names, banned phrases, required disclaimers and channel limits, with one-click fixes." },
  { icon: FileSearch, title: "Claims", tag: "AI · verified in code",
    text: "Every claim is matched to approved evidence with an owner and an expiry date. Cited quotes are checked word for word." },
  { icon: MessageSquareQuote, title: "Voice", tag: "Advisory",
    text: "Notes against your brand voice rubric. They help the writer and never block approval." },
];

const STEPS = [
  { title: "Submit", text: "Paste copy or upload DOCX/PDF with a one-line purpose." },
  { title: "Check", text: "Rules, claims and voice run in parallel." },
  { title: "Revise", text: "Accept fixes that keep the purpose, or explain why not." },
  { title: "Countersign", text: "A reviewer approves, with every decision recorded." },
];

const TRUST = [
  { icon: UserCheck, title: "A person signs last", text: "AI never publishes, never applies a change on its own and never edits the rulebook." },
  { icon: ShieldCheck, title: "Evidence, not opinion", text: "Only written rules and approved facts can block approval. Tone notes stay advisory." },
  { icon: History, title: "Tamper-evident history", text: "Versions, decisions and reasons sit in a hash-chained audit log you can export." },
];

/** A static picture of the review screen: real highlight styles, illustrative content. */
function Preview() {
  return (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-white text-ink shadow-2xl shadow-black/40" aria-hidden>
      <div className="flex items-center gap-1.5 border-b border-line bg-canvas px-4 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-slate-300" /><span className="h-2.5 w-2.5 rounded-full bg-slate-300" />
        <span className="h-2.5 w-2.5 rounded-full bg-slate-300" />
        <span className="ml-3 truncate text-xs text-ink-faint">AloeCalm launch caption · Instagram · v1</span>
      </div>
      <div className="grid sm:grid-cols-[1fr_210px]">
        <p className="px-4 py-4 text-[13px] leading-7 sm:px-5">
          Meet the new <span className="hl hl-rules">Aloe-Calm</span> gel: <span className="hl hl-claims">100% natural</span> and{" "}
          <span className="hl hl-claims">clinically proven to clear acne in just 7 days</span>
          <span className="hl hl-rules">!!!</span> <span className="hl hl-claims">Free delivery on every order</span>, this week only.
        </p>
        <div className="space-y-2 border-t border-line bg-canvas/70 p-3 sm:border-l sm:border-t-0">
          {[
            ["hl-badge-rules", "Rules · R03", "Use “AloeCalm”"],
            ["hl-badge-claims", "Claim · Contradicted", "F-19: 68% in four weeks"],
            ["hl-badge-claims", "Claim · Unsupported", "No approved fact"],
          ].map(([cls, badge, text]) => (
            <div key={badge} className="rounded-lg border border-line bg-white p-2.5">
              <span className={`hl-badge ${cls} !mx-0`}>{badge}</span>
              <p className="mt-1 text-xs text-ink-soft">{text}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function Landing() {
  const nav = useNavigate();
  const reset = useResetSession();
  const { data: me } = useMe();
  const [busy, setBusy] = useState<Role | null>(null);
  const [error, setError] = useState<unknown>(null);

  const start = async (role: Role) => {
    setBusy(role);
    setError(null);
    try {
      await api.post("/api/demo/session", { role });
      await reset();
      nav(role === "creator" ? "/drafts/new?sample=1" : role === "reviewer" ? "/queue" : "/admin/rules");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="min-h-dvh bg-white">
      <section className="hero-grid text-white" style={{ paddingTop: "env(safe-area-inset-top)" }}>
        <header className="mx-auto flex max-w-7xl items-center justify-between px-4 py-5 sm:px-6 lg:px-8">
          <Logo light />
          <div className="flex items-center gap-5 text-sm">
            {me && <Link to="/drafts" className="font-medium text-white hover:text-brand-100">Open workspace</Link>}
            <a href="https://github.com/Gauravtiwari31/CounterSign" className="text-slate-300 hover:text-white">GitHub</a>
          </div>
        </header>

        <div className="mx-auto grid max-w-7xl items-center gap-12 px-4 pb-20 pt-8 sm:px-6 md:pt-14 lg:grid-cols-[1.05fr_1fr] lg:gap-16 lg:px-8 lg:pb-28">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-medium text-slate-200">
              <ShieldCheck className="h-3.5 w-3.5 text-brand-100" /> Pre-publication brand governance
            </p>
            <h1 className="mt-5 text-[2rem] font-semibold leading-[1.15] tracking-tight sm:text-5xl lg:text-[3.25rem]">
              Review every claim before it goes public.
            </h1>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-slate-300 sm:text-lg">
              Countersign checks marketing copy against your rulebook and approved evidence, explains each finding,
              suggests fixes that keep the writer’s intent, and routes the draft to a reviewer for sign-off.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
              <Button variant="primary" className="px-5 py-2.5 text-[15px]" busy={busy === "creator"} onClick={() => start("creator")}>
                Try as Creator <ArrowRight className="h-4 w-4" />
              </Button>
              <Button className="border-white/20 bg-white/10 px-5 py-2.5 text-[15px] text-white shadow-none hover:border-white/30 hover:bg-white/15"
                busy={busy === "reviewer"} onClick={() => start("reviewer")}>Try as Reviewer</Button>
              <Button className="border-white/20 bg-white/10 px-5 py-2.5 text-[15px] text-white shadow-none hover:border-white/30 hover:bg-white/15"
                busy={busy === "admin"} onClick={() => start("admin")}>Try as Admin</Button>
            </div>
            <p className="mt-4 text-sm text-slate-400">
              No sign-up. Each visitor gets a private sandbox with a fictional brand, Verdant Skin.
            </p>
            {error != null && <div className="mt-4 max-w-xl"><ErrorNote error={error} /></div>}
          </div>
          <Preview />
        </div>
      </section>

      <section className="border-b border-line">
        <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
          <p className="text-sm font-semibold text-brand-600">Three lanes, three levels of authority</p>
          <h2 className="mt-2 max-w-2xl text-2xl font-semibold tracking-tight sm:text-3xl">
            Automation that explains itself and knows its limits.
          </h2>
          <div className="mt-10 grid gap-5 md:grid-cols-3">
            {LANES.map((l) => (
              <div key={l.title} className="rounded-xl border border-line bg-white p-6 shadow-card">
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                  <l.icon className="h-5 w-5" aria-hidden /></span>
                <p className="mt-4 font-semibold">{l.title}</p>
                <p className="mt-0.5 text-xs font-medium uppercase tracking-wide text-ink-faint">{l.tag}</p>
                <p className="mt-3 text-sm leading-relaxed text-ink-soft">{l.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-canvas">
        <div className="mx-auto grid max-w-7xl gap-12 px-4 py-16 sm:px-6 lg:grid-cols-2 lg:px-8 lg:py-20">
          <div>
            <p className="text-sm font-semibold text-brand-600">Workflow</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">From draft to countersign</h2>
            <ol className="mt-8 space-y-5">
              {STEPS.map((s, i) => (
                <li key={s.title} className="flex gap-4">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink text-sm font-medium text-white">{i + 1}</span>
                  <div><p className="font-medium">{s.title}</p><p className="text-sm text-ink-soft">{s.text}</p></div>
                </li>
              ))}
            </ol>
          </div>
          <div className="grid gap-4">
            {TRUST.map((t) => (
              <div key={t.title} className="flex gap-4 rounded-xl border border-line bg-white p-5 shadow-card">
                <t.icon className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" aria-hidden />
                <div><p className="font-medium">{t.title}</p><p className="mt-1 text-sm leading-relaxed text-ink-soft">{t.text}</p></div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="border-t border-line bg-white" style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-6 text-xs text-ink-faint sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
          <span>© 2026 Countersign · Team Ship It Friday</span>
          <span>All brands, products and data in the demo are fictional.</span>
        </div>
      </footer>
    </div>
  );
}
