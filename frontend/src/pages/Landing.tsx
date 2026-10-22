import { BookCheck, FileSearch, MessageSquareQuote, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Role } from "../api/types";
import { Logo } from "../components/Layout";
import { Button, ErrorNote } from "../components/ui";
import { useMe, useResetSession } from "../hooks";

const LANES = [
  { icon: BookCheck, title: "Rules lane", tag: "Deterministic, instant",
    text: "Your rulebook, applied word by word: product names, banned phrases, required disclaimers, limits. One-click fixes." },
  { icon: FileSearch, title: "Claims lane", tag: "AI + verification in code",
    text: "Every claim is matched to your approved evidence. Quotes are verified word for word, so a citation can never be invented." },
  { icon: MessageSquareQuote, title: "Voice lane", tag: "Advisory only",
    text: "Notes against your brand voice rubric. Helpful, never blocking." },
];

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
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5">
        <Logo />
        <div className="flex items-center gap-4 text-sm">
          {me && <Link to="/drafts" className="font-medium text-leaf-600">Back to your sandbox →</Link>}
          <a href="https://github.com/Gauravtiwari31/CounterSign" className="text-ink-soft hover:text-ink">GitHub</a>
        </div>
      </header>

      <section className="mx-auto max-w-6xl px-4 pb-10 pt-10 md:pt-16">
        <p className="mb-3 inline-flex items-center gap-1.5 rounded-full bg-leaf-100 px-3 py-1 text-xs font-medium text-leaf-700">
          <ShieldCheck className="h-3.5 w-3.5" /> Brand governance for marketing teams
        </p>
        <h1 className="max-w-3xl font-serif text-4xl font-semibold leading-tight md:text-5xl">
          Catch off-brand words and unproven claims before they ship, then get a human countersign.
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-ink-soft">
          Paste a caption, email or product blurb. Countersign checks it against your rulebook and your approved
          evidence, suggests fixes that keep your intent, and routes it to a reviewer with a full audit trail.
        </p>

        <div className="mt-8 rounded-2xl border border-ink/10 bg-white p-5 md:p-6">
          <p className="font-medium">Try it now, no sign-up</p>
          <div className="mt-3 flex flex-wrap gap-3">
            <Button variant="primary" className="px-5 py-2.5 text-base" busy={busy === "creator"} onClick={() => start("creator")}>
              Try as Creator
            </Button>
            <Button className="px-5 py-2.5 text-base" busy={busy === "reviewer"} onClick={() => start("reviewer")}>Reviewer</Button>
            <Button className="px-5 py-2.5 text-base" busy={busy === "admin"} onClick={() => start("admin")}>Admin</Button>
          </div>
          <p className="mt-3 text-sm text-ink-soft">
            Each visitor gets a private sandbox with a fictional brand, Verdant Skin. Switch roles any time from the header.
          </p>
          <div className="mt-3"><ErrorNote error={error} /></div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-16">
        <h2 className="mb-4 font-serif text-2xl font-semibold">How it works</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {LANES.map((l) => (
            <div key={l.title} className="rounded-xl border border-ink/10 bg-white p-5">
              <l.icon className="h-5 w-5 text-leaf-500" aria-hidden />
              <p className="mt-3 font-semibold">{l.title}</p>
              <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">{l.tag}</p>
              <p className="mt-2 text-sm text-ink-soft">{l.text}</p>
            </div>
          ))}
        </div>
        <ol className="mt-8 grid gap-3 text-sm md:grid-cols-4">
          {["Creator submits a draft", "Three lanes check it", "Creator fixes or explains", "Reviewer countersigns"].map((s, i) => (
            <li key={s} className="flex items-center gap-3 rounded-lg bg-ink/[0.03] px-4 py-3">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-ink text-xs text-white">{i + 1}</span> {s}
            </li>
          ))}
        </ol>
      </section>
      <footer className="border-t border-ink/10 py-6 text-center text-xs text-ink-faint">
        Team SHIP IT FRIDAY · Inkloom AI brand-governance problem statement · All brands and data in the demo are fictional.
      </footer>
    </div>
  );
}
