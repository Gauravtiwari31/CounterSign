import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { HOME, Logo } from "../components/Layout";
import { useMe } from "../hooks";

const WRAP = "mx-auto w-full max-w-[1720px] px-5 sm:px-8 lg:px-14";

const LANES = [
  { title: "Rules", tag: "Deterministic", text: "Product names, banned and required phrases, disclaimers and channel limits, checked the same way every time, with one-click fixes." },
  { title: "Claims", tag: "Evidence-backed", text: "Each claim is matched to an approved fact with an owner and an expiry date. Cited quotes are verified word for word." },
  { title: "Voice", tag: "Advisory", text: "Notes against your brand voice. They help the writer and never block approval." },
];

const STEPS = [
  ["Submit", "A creator pastes copy or uploads a DOCX or PDF, with a one-line purpose."],
  ["Check", "Rules, claims and voice run together. Every finding cites the rule or fact behind it."],
  ["Revise", "The creator accepts fixes that keep the purpose, or explains why the text should stay."],
  ["Countersign", "A second person approves. Every version, decision and reason is kept in the history."],
];

const ROLES = [
  ["Admin", "Sets up the rulebook and approved facts, and invites the team."],
  ["Creator", "Writes drafts, fixes findings and sends them for review."],
  ["Reviewer", "Checks the claims ledger and countersigns, or sends the draft back."],
];

export default function Landing() {
  const { data: me } = useMe();
  const cta = me
    ? <Link to={HOME[me.user.role]} className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-ink px-5 text-[15px] font-medium text-white hover:bg-slate-800">Open workspace <ArrowRight className="h-4 w-4" /></Link>
    : <Link to="/signup" className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-ink px-5 text-[15px] font-medium text-white hover:bg-slate-800">Create a workspace <ArrowRight className="h-4 w-4" /></Link>;

  return (
    <div className="min-h-dvh bg-white text-ink">
      <header className="border-b border-line" style={{ paddingTop: "env(safe-area-inset-top)" }}>
        <div className={`${WRAP} flex h-16 items-center justify-between`}>
          <Logo />
          <nav className="flex items-center gap-2 text-sm sm:gap-4">
            {me ? null : <Link to="/login" className="rounded-lg px-3 py-2 font-medium text-ink-soft hover:text-ink">Sign in</Link>}
            {me ? null : <Link to="/signup" className="hidden rounded-lg border border-line px-3 py-2 font-medium hover:bg-slate-50 sm:inline-block">Create workspace</Link>}
          </nav>
        </div>
      </header>

      <section className={`${WRAP} grid gap-12 py-16 sm:py-20 lg:grid-cols-12 lg:gap-16 lg:py-28`}>
        <div className="lg:col-span-7">
          <p className="text-sm font-medium text-ink-faint">Pre-publication review for marketing teams</p>
          <h1 className="mt-4 text-[2.25rem] font-semibold leading-[1.1] tracking-tight sm:text-5xl xl:text-6xl">
            Every claim checked. Every approval signed by a person.
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-ink-soft">
            Countersign checks captions, emails and product copy against your rulebook and approved evidence before
            they are published. Writers get specific, explained feedback; reviewers see exactly what each claim rests on.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            {cta}
            {!me && <Link to="/login" className="inline-flex min-h-[44px] items-center rounded-lg border border-line px-5 text-[15px] font-medium hover:bg-slate-50">Sign in</Link>}
          </div>
        </div>
        <dl className="divide-y divide-line self-start overflow-hidden rounded-xl border border-line bg-white lg:col-span-5">
          {ROLES.map(([role, text]) => (
            <div key={role} className="bg-white p-5 sm:p-6">
              <dt className="font-medium">{role}</dt>
              <dd className="mt-1 text-sm leading-relaxed text-ink-soft">{text}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="border-t border-line bg-canvas">
        <div className={`${WRAP} py-16 sm:py-20`}>
          <h2 className="max-w-3xl text-2xl font-semibold tracking-tight sm:text-3xl">Three checks, each with a clear level of authority</h2>
          <p className="mt-3 max-w-3xl text-ink-soft">Only written rules and approved facts can block approval. AI never publishes, never applies a change on its own and never edits the rulebook.</p>
          <div className="mt-10 grid gap-5 md:grid-cols-3">
            {LANES.map((l) => (
              <div key={l.title} className="rounded-xl border border-line bg-white p-6">
                <div className="flex items-baseline justify-between gap-3">
                  <p className="text-lg font-semibold">{l.title}</p>
                  <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">{l.tag}</p>
                </div>
                <p className="mt-3 text-sm leading-relaxed text-ink-soft">{l.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-t border-line">
        <div className={`${WRAP} py-16 sm:py-20`}>
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">How a draft gets approved</h2>
          <ol className="mt-10 grid gap-8 sm:grid-cols-2 xl:grid-cols-4">
            {STEPS.map(([title, text], i) => (
              <li key={title} className="border-t-2 border-ink pt-4">
                <p className="text-sm text-ink-faint">0{i + 1}</p>
                <p className="mt-1 font-semibold">{title}</p>
                <p className="mt-2 text-sm leading-relaxed text-ink-soft">{text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <footer className="border-t border-line" style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
        <div className={`${WRAP} flex flex-col gap-2 py-6 text-sm text-ink-faint sm:flex-row sm:items-center sm:justify-between`}>
          <span>© 2026 Countersign</span>
          <a href="https://github.com/Gauravtiwari31/CounterSign" className="hover:text-ink">GitHub</a>
        </div>
      </footer>
    </div>
  );
}
