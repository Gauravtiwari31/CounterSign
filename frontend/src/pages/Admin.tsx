import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import type { Criterion, Fact, Palette, Rule, Services } from "../api/types";
import { Badge, Button, Card, ErrorNote, Modal, Spinner } from "../components/ui";
import { useMe } from "../hooks";

const RULE_TEMPLATES: Record<string, Record<string, unknown>> = {
  terminology: { preferred: "AloeCalm", forbidden: ["Aloe-Calm"] },
  banned_phrase: { phrases: ["guaranteed results"], alternative: null },
  required_phrase: { text: "T&C apply", trigger: "\\d+\\s?%\\s?off", position: "any" },
  punctuation_limit: { char: "!", max_per_draft: 1, max_run: 1 },
  length_limit: { limits: { x: { max_chars: 280 } } },
  readability: { max_sentence_words: 30, min_flesch: 40 },
  all_caps: { allow: ["SPF"], min_length: 4 },
  hashtag: { max_count: 5, required: ["#VerdantSkin"] },
  regex: { pattern: "\\b(\\d+)\\s?per\\s?cent\\b", flags: "i", message: "Use the % sign", replacement: "\\1%",
           should_match: ["20 per cent"], should_not_match: ["percentage"] },
  currency_format: { symbol: "₹" },
};
const SEV_TONE = { blocking: "red", warning: "amber", info: "neutral" } as const;
const input = "field";

type RuleDraft = Omit<Rule, "id" | "introduced_in" | "retired_in"> & { id?: string };

function RuleEditor({ initial, onClose }: { initial: RuleDraft; onClose: () => void }) {
  const qc = useQueryClient();
  const [r, setR] = useState(initial);
  const [params, setParams] = useState(JSON.stringify(initial.params, null, 2));
  const [sample, setSample] = useState("Say hello to Aloe-Calm!!! Now 20 per cent off at Rs. 499.");
  const parsed = (() => { try { return JSON.parse(params); } catch { return null; } })();
  const body = { ...r, params: parsed ?? {}, channels: r.channels?.length ? r.channels : null };
  const test = useMutation({
    mutationFn: () => api.post<{ ok: boolean; errors: string[]; hits: { text: string; message: string; replacement: string | null }[] }>(
      "/api/rules/test", { rule: body, text: sample }),
  });
  const save = useMutation({
    mutationFn: () => (r.id ? api.put(`/api/rules/${r.id}`, body) : api.post("/api/rules", body)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["rules"] }); qc.invalidateQueries({ queryKey: ["me"] }); onClose(); },
  });
  return (
    <form className="space-y-3 text-sm" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <div className="grid gap-3 sm:grid-cols-3">
        <label>Code<input className={input} value={r.code} onChange={(e) => setR({ ...r, code: e.target.value })} placeholder="R15" required /></label>
        <label>Type
          <select className={input} value={r.type} disabled={!!r.id}
            onChange={(e) => { setR({ ...r, type: e.target.value }); setParams(JSON.stringify(RULE_TEMPLATES[e.target.value], null, 2)); }}>
            {Object.keys(RULE_TEMPLATES).map((t) => <option key={t}>{t}</option>)}
          </select></label>
        <label>Severity
          <select className={input} value={r.severity} onChange={(e) => setR({ ...r, severity: e.target.value as Rule["severity"] })}>
            <option>blocking</option><option>warning</option><option>info</option>
          </select></label>
      </div>
      <label className="block">Title<input className={input} value={r.title} onChange={(e) => setR({ ...r, title: e.target.value })} required /></label>
      <label className="block">Explanation shown to creators<input className={input} value={r.description} onChange={(e) => setR({ ...r, description: e.target.value })} /></label>
      <label className="block">Channels (comma separated, empty = all)
        <input className={input} value={(r.channels ?? []).join(", ")} onChange={(e) => setR({ ...r, channels: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} /></label>
      <label className="block">Parameters (JSON)
        <textarea className={`${input} font-mono text-xs`} rows={6} value={params} onChange={(e) => setParams(e.target.value)} />
        {!parsed && <span className="text-xs text-red-700">Not valid JSON</span>}
      </label>
      <div className="rounded-lg bg-ink/[0.03] p-3">
        <p className="font-medium">Test this rule</p>
        <textarea className={input} rows={2} value={sample} onChange={(e) => setSample(e.target.value)} aria-label="Test text" />
        <Button type="button" className="mt-2" onClick={() => test.mutate()} busy={test.isPending} disabled={!parsed}>Run test</Button>
        {test.data && (
          <ul className="mt-2 space-y-1">
            {test.data.errors.map((e) => <li key={e} className="text-red-700">{e}</li>)}
            {test.data.ok && test.data.hits.length === 0 && <li className="text-ink-soft">No matches.</li>}
            {test.data.hits.map((h, i) => <li key={i}>“{h.text}” · {h.message}{h.replacement != null && <> → <b>{h.replacement}</b></>}</li>)}
          </ul>
        )}
      </div>
      <ErrorNote error={save.error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
        <Button type="submit" variant="primary" busy={save.isPending} disabled={!parsed}>{r.id ? "Save as new rulebook version" : "Add rule"}</Button>
      </div>
    </form>
  );
}

export function RulesPage() {
  const qc = useQueryClient();
  const { data: me } = useMe();
  const isAdmin = me?.user.role === "admin";
  const q = useQuery({ queryKey: ["rules"], queryFn: () => api.get<{ rulebook_version: number; rules: Rule[] }>("/api/rules") });
  const [editing, setEditing] = useState<RuleDraft | null>(null);
  const retire = useMutation({
    mutationFn: (id: string) => api.del(`/api/rules/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rules"] }),
  });
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="page-title">Rulebook <Badge tone="blue">version {q.data?.rulebook_version ?? "…"}</Badge></h1>
          <p className="text-sm text-ink-soft">Deterministic checks. Every edit creates a new rulebook version; each review records the version it used.</p>
        </div>
        {isAdmin && <Button variant="primary" onClick={() => setEditing({ code: "", type: "banned_phrase", params: RULE_TEMPLATES.banned_phrase, severity: "warning", channels: null, title: "", description: "" })}>
          <Plus className="h-4 w-4" /> Add rule</Button>}
      </div>
      {q.isLoading && <Spinner />}<ErrorNote error={q.error ?? retire.error} />
      <div className="grid gap-3 md:grid-cols-2">
        {q.data?.rules.map((r) => (
          <Card key={r.id} className="p-4 text-sm">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-medium"><code className="mr-1.5 text-xs text-ink-faint">{r.code}</code>{r.title}</p>
                <p className="mt-0.5 text-xs text-ink-faint">{r.type}{r.channels ? ` · ${r.channels.join(", ")}` : ""} · since v{r.introduced_in}</p>
              </div>
              <Badge tone={SEV_TONE[r.severity]}>{r.severity}</Badge>
            </div>
            <p className="mt-2 text-ink-soft">{r.description}</p>
            {isAdmin && (
              <div className="mt-3 flex gap-1.5">
                <Button className="px-2.5 py-1 text-xs" onClick={() => setEditing(r)}><Pencil className="h-3.5 w-3.5" /> Edit</Button>
                <Button variant="ghost" className="px-2.5 py-1 text-xs" onClick={() => confirm(`Retire ${r.code}?`) && retire.mutate(r.id)}>
                  <Trash2 className="h-3.5 w-3.5" /> Retire</Button>
              </div>
            )}
          </Card>
        ))}
      </div>
      <Modal open={!!editing} title={editing?.id ? `Edit ${editing.code}` : "Add rule"} onClose={() => setEditing(null)}>
        {editing && <RuleEditor key={editing.id ?? "new"} initial={editing} onClose={() => setEditing(null)} />}
      </Modal>
    </div>
  );
}

const STATUS_TONE = { valid: "green", expiring_soon: "amber", expired: "red", superseded: "neutral" } as const;
type FactDraft = Partial<Fact>;

function FactEditor({ initial, facts, onClose }: { initial: FactDraft; facts: Fact[]; onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState(initial);
  const list = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
  const body = {
    code: f.code, statement: f.statement, source_document: f.source_document ?? "", source_locator: f.source_locator ?? "",
    owner: f.owner ?? "", scope_products: f.scope_products ?? [], scope_channels: f.scope_channels ?? [],
    scope_regions: f.scope_regions ?? [], valid_from: f.valid_from || null, valid_to: f.valid_to || null,
    superseded_by: f.superseded_by || null,
  };
  const save = useMutation({
    mutationFn: () => (f.id ? api.put(`/api/facts/${f.id}`, body) : api.post("/api/facts", body)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["facts"] }); onClose(); },
  });
  return (
    <form className="space-y-3 text-sm" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <div className="grid grid-cols-[120px_1fr] gap-3">
        <label>Code<input className={input} value={f.code ?? ""} onChange={(e) => setF({ ...f, code: e.target.value })} placeholder="F-50" required /></label>
        <label>Owner<input className={input} value={f.owner ?? ""} onChange={(e) => setF({ ...f, owner: e.target.value })} /></label>
      </div>
      <label className="block">Approved statement
        <textarea className={input} rows={3} value={f.statement ?? ""} onChange={(e) => setF({ ...f, statement: e.target.value })} required /></label>
      <div className="grid gap-3 sm:grid-cols-2">
        <label>Source document<input className={input} value={f.source_document ?? ""} onChange={(e) => setF({ ...f, source_document: e.target.value })} /></label>
        <label>Locator (page, table)<input className={input} value={f.source_locator ?? ""} onChange={(e) => setF({ ...f, source_locator: e.target.value })} /></label>
        <label>Valid from<input type="date" className={input} value={f.valid_from ?? ""} onChange={(e) => setF({ ...f, valid_from: e.target.value })} /></label>
        <label>Valid to<input type="date" className={input} value={f.valid_to ?? ""} onChange={(e) => setF({ ...f, valid_to: e.target.value })} /></label>
        <label>Products (comma separated)<input className={input} value={(f.scope_products ?? []).join(", ")} onChange={(e) => setF({ ...f, scope_products: list(e.target.value) })} /></label>
        <label>Superseded by
          <select className={input} value={f.superseded_by ?? ""} onChange={(e) => setF({ ...f, superseded_by: e.target.value || null })}>
            <option value="">—</option>
            {facts.filter((x) => x.id !== f.id).map((x) => <option key={x.id} value={x.id}>{x.code}</option>)}
          </select></label>
      </div>
      <ErrorNote error={save.error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
        <Button type="submit" variant="primary" busy={save.isPending}>{f.id ? "Save as new version" : "Add fact"}</Button>
      </div>
    </form>
  );
}

export function FactsPage() {
  const qc = useQueryClient();
  const { data: me } = useMe();
  const isAdmin = me?.user.role === "admin";
  const q = useQuery({ queryKey: ["facts"], queryFn: () => api.get<{ facts_version: number; facts: Fact[] }>("/api/facts") });
  const [editing, setEditing] = useState<FactDraft | null>(null);
  const retire = useMutation({ mutationFn: (id: string) => api.del(`/api/facts/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["facts"] }) });
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="page-title">Evidence library <Badge tone="blue">version {q.data?.facts_version ?? "…"}</Badge></h1>
          <p className="text-sm text-ink-soft">Approved facts that claims are checked against. Expired and superseded facts stay visible so outdated claims are caught.</p>
        </div>
        {isAdmin && <Button variant="primary" onClick={() => setEditing({})}><Plus className="h-4 w-4" /> Add fact</Button>}
      </div>
      {q.isLoading && <Spinner />}<ErrorNote error={q.error} />
      {q.data && (
        <div className="overflow-x-auto table-wrap">
          <table className="w-full text-sm">
            <thead className="table-head">
              <tr><th className="px-4 py-2.5">Code</th><th className="px-4">Statement</th><th className="px-4">Owner</th><th className="px-4">Source</th><th className="px-4">Status</th><th className="px-4" /></tr>
            </thead>
            <tbody>
              {q.data.facts.map((f) => (
                <tr key={f.id} className="border-b border-ink/5 align-top last:border-0">
                  <td className="whitespace-nowrap px-4 py-3 font-medium">{f.code}</td>
                  <td className="px-4 py-3">{f.statement}{f.scope_products.length > 0 && <p className="text-xs text-ink-faint">{f.scope_products.join(", ")}</p>}</td>
                  <td className="px-4 py-3">{f.owner}</td>
                  <td className="px-4 py-3 text-ink-soft">{f.source_document}{f.source_locator && `, ${f.source_locator}`}</td>
                  <td className="px-4 py-3">
                    <Badge tone={STATUS_TONE[f.status]}>{f.status.replace("_", " ")}</Badge>
                    {f.valid_to && <p className="text-xs text-ink-faint">to {f.valid_to}</p>}
                    {f.superseded_by_code && <p className="text-xs text-ink-faint">by {f.superseded_by_code}</p>}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    {isAdmin && <>
                      <button className="rounded p-1 hover:bg-ink/5" aria-label={`Edit ${f.code}`} onClick={() => setEditing(f)}><Pencil className="h-4 w-4" /></button>
                      <button className="rounded p-1 hover:bg-ink/5" aria-label={`Retire ${f.code}`} onClick={() => confirm(`Retire ${f.code}?`) && retire.mutate(f.id)}><Trash2 className="h-4 w-4" /></button>
                    </>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Modal open={!!editing} title={editing?.id ? `Edit ${editing.code}` : "Add fact"} onClose={() => setEditing(null)}>
        {editing && <FactEditor key={editing.id ?? "new"} initial={editing} facts={q.data?.facts ?? []} onClose={() => setEditing(null)} />}
      </Modal>
    </div>
  );
}

export function VoicePage() {
  const qc = useQueryClient();
  const { data: me } = useMe();
  const q = useQuery({ queryKey: ["voice"], queryFn: () => api.get<Criterion[]>("/api/voice-criteria") });
  const [editing, setEditing] = useState<Partial<Criterion> | null>(null);
  const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);
  const save = useMutation({
    mutationFn: (c: Partial<Criterion>) => {
      const body = { code: c.code, title: c.title, description: c.description ?? "", good_examples: c.good_examples ?? [], bad_examples: c.bad_examples ?? [] };
      return c.id ? api.put(`/api/voice-criteria/${c.id}`, body) : api.post("/api/voice-criteria", body);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["voice"] }); setEditing(null); },
  });
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="page-title">Voice rubric</h1>
          <p className="text-sm text-ink-soft">The voice lane is advisory: it can suggest, never block.</p>
        </div>
        {me?.user.role === "admin" && <Button variant="primary" onClick={() => setEditing({})}><Plus className="h-4 w-4" /> Add criterion</Button>}
      </div>
      {q.isLoading && <Spinner />}<ErrorNote error={q.error} />
      <div className="grid gap-3 md:grid-cols-2">
        {q.data?.map((c) => (
          <Card key={c.id} className="p-4 text-sm">
            <div className="flex justify-between gap-2">
              <p className="font-medium"><code className="mr-1.5 text-xs text-ink-faint">{c.code}</code>{c.title}</p>
              {me?.user.role === "admin" && <button className="rounded p-1 hover:bg-ink/5" aria-label={`Edit ${c.code}`} onClick={() => setEditing(c)}><Pencil className="h-4 w-4" /></button>}
            </div>
            <p className="mt-1 text-ink-soft">{c.description}</p>
            {c.good_examples.map((g) => <p key={g} className="mt-1.5 text-leaf-700">✓ “{g}”</p>)}
            {c.bad_examples.map((b) => <p key={b} className="mt-1 text-red-800">✗ “{b}”</p>)}
          </Card>
        ))}
      </div>
      <Modal open={!!editing} title={editing?.id ? `Edit ${editing.code}` : "Add criterion"} onClose={() => setEditing(null)}>
        {editing && (
          <form className="space-y-3 text-sm" onSubmit={(e) => { e.preventDefault(); save.mutate(editing); }}>
            <div className="grid grid-cols-[100px_1fr] gap-3">
              <label>Code<input className={input} value={editing.code ?? ""} onChange={(e) => setEditing({ ...editing, code: e.target.value })} placeholder="V5" required /></label>
              <label>Title<input className={input} value={editing.title ?? ""} onChange={(e) => setEditing({ ...editing, title: e.target.value })} required /></label>
            </div>
            <label className="block">Description<textarea className={input} rows={2} value={editing.description ?? ""} onChange={(e) => setEditing({ ...editing, description: e.target.value })} /></label>
            <label className="block">Good examples (one per line)<textarea className={input} rows={2} value={(editing.good_examples ?? []).join("\n")} onChange={(e) => setEditing({ ...editing, good_examples: lines(e.target.value) })} /></label>
            <label className="block">Bad examples (one per line)<textarea className={input} rows={2} value={(editing.bad_examples ?? []).join("\n")} onChange={(e) => setEditing({ ...editing, bad_examples: lines(e.target.value) })} /></label>
            <ErrorNote error={save.error} />
            <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button><Button type="submit" variant="primary" busy={save.isPending}>Save</Button></div>
          </form>
        )}
      </Modal>
    </div>
  );
}

export function PalettePage() {
  const qc = useQueryClient();
  const { data: me } = useMe();
  const q = useQuery({ queryKey: ["palette"], queryFn: () => api.get<Palette>("/api/palette") });
  const [draft, setDraft] = useState<Palette["colors"] | null>(null);
  const save = useMutation({
    mutationFn: (colors: Palette["colors"]) => api.put<Palette>("/api/palette", colors),
    onSuccess: (data) => { qc.setQueryData(["palette"], data); setDraft(null); },
  });
  const colors = draft ?? q.data?.colors ?? [];
  return (
    <div>
      <h1 className="page-title">Brand palette</h1>
      <p className="mb-4 text-sm text-ink-soft">WCAG 2.1 contrast for every declared foreground/background pair. Pass and fail are written out, not only coloured.</p>
      {q.isLoading && <Spinner />}<ErrorNote error={q.error ?? save.error} />
      <div className="grid gap-5 xl:grid-cols-[360px_1fr]">
        <Card className="p-4 text-sm">
          <ul className="space-y-2">
            {colors.map((c, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2">
                <span className="h-7 w-7 shrink-0 rounded border border-line" style={{ background: c.hex }} aria-hidden />
                {draft ? (
                  <>
                    <input className="w-24 rounded border border-line px-1.5 py-1" value={c.name} aria-label="Name" onChange={(e) => setDraft(colors.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} />
                    <input className="w-20 rounded border border-line px-1.5 py-1 font-mono text-xs" value={c.hex} aria-label="Hex" onChange={(e) => setDraft(colors.map((x, j) => j === i ? { ...x, hex: e.target.value } : x))} />
                    <select className="rounded border border-line bg-white px-1 py-1" value={c.role} aria-label="Role" onChange={(e) => setDraft(colors.map((x, j) => j === i ? { ...x, role: e.target.value as typeof c.role } : x))}>
                      <option>text</option><option>background</option><option>accent</option></select>
                    <button aria-label="Remove" onClick={() => setDraft(colors.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></button>
                  </>
                ) : <span>{c.name} <code className="text-xs text-ink-faint">{c.hex}</code> · {c.role}</span>}
              </li>
            ))}
          </ul>
          {me?.user.role === "admin" && (draft ? (
            <div className="mt-3 flex flex-wrap gap-2">
              <Button onClick={() => setDraft([...colors, { name: "New", hex: "#000000", role: "accent" }])}><Plus className="h-4 w-4" /> Colour</Button>
              <Button variant="primary" busy={save.isPending} onClick={() => save.mutate(colors)}>Save</Button>
              <Button variant="ghost" onClick={() => setDraft(null)}>Cancel</Button>
            </div>
          ) : <Button className="mt-3" onClick={() => setDraft(colors)}><Pencil className="h-4 w-4" /> Edit palette</Button>)}
        </Card>
        <div className="overflow-x-auto table-wrap">
          <table className="w-full text-sm">
            <thead className="table-head">
              <tr><th className="px-4 py-2.5">Sample</th><th className="px-4">Text on background</th><th className="px-4">Ratio</th><th className="px-4">AA normal</th><th className="px-4">AA large</th><th className="px-4">AAA</th></tr>
            </thead>
            <tbody>
              {q.data?.matrix.map((m, i) => (
                <tr key={i} className="border-b border-ink/5 last:border-0">
                  <td className="px-4 py-2"><span className="rounded px-2 py-1 text-sm font-medium" style={{ color: m.foreground_hex, background: m.background_hex }}>Aa</span></td>
                  <td className="px-4">{m.foreground} on {m.background}</td>
                  <td className="px-4 font-mono">{m.ratio.toFixed(2)}:1</td>
                  {[m.aa_normal, m.aa_large, m.aaa_normal].map((ok, j) => (
                    <td key={j} className="px-4"><Badge tone={ok ? "green" : "red"}>{ok ? "Pass" : "Fail"}</Badge></td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export function SettingsPage() {
  const q = useQuery({ queryKey: ["services"], queryFn: () => api.get<Services>("/api/settings/services") });
  const { data: me } = useMe();
  if (q.isLoading) return <Spinner />;
  if (!q.data) return <ErrorNote error={q.error} />;
  const s = q.data;
  const rows: [string, string][] = [
    ["Language model", s.llm.length ? s.llm.map((l) => `${l.provider} ${l.model} (${l.role})`).join(" · ") : "Not configured"],
    ["Model data use", s.llm_data_use],
    ["What is sent", s.data_sent_to_llm],
    ["Personal data masking", s.pii_masking],
    ["Embeddings", s.embeddings],
    ["Database", s.database],
    ["Hosting", s.hosting],
  ];
  return (
    <div className="max-w-3xl">
      <h1 className="page-title">Settings · External services</h1>
      <p className="mb-4 text-sm text-ink-soft">Every service that touches your content, and what it receives. Findings are labelled “AI” or “Rule” everywhere.</p>
      {s.llm_note && <p className="mb-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{s.llm_note}</p>}
      <Card>
        <dl className="divide-y divide-ink/5 text-sm">
          {rows.map(([k, v]) => (
            <div key={k} className="grid gap-1 px-4 py-3 sm:grid-cols-[200px_1fr]"><dt className="font-medium">{k}</dt><dd className="text-ink-soft">{v}</dd></div>
          ))}
          {me && <div className="grid gap-1 px-4 py-3 sm:grid-cols-[200px_1fr]"><dt className="font-medium">Workspace</dt>
            <dd className="text-ink-soft">{me.org.name} · rulebook v{me.org.rulebook_version} · facts v{me.org.facts_version}
              {me.org.expires_at && ` · sandbox expires ${new Date(me.org.expires_at).toLocaleString()}`}</dd></div>}
        </dl>
      </Card>
    </div>
  );
}
