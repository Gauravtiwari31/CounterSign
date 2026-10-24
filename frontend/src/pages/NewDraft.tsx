import { useMutation, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Sparkles, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { Channel } from "../api/types";
import { CHANNEL_LABEL } from "../api/types";
import { Button, Card, ErrorNote } from "../components/ui";
import { markStep, useMe } from "../hooks";

interface Sample { title: string; channel: Channel; purpose: string; text: string }

export default function NewDraft() {
  const nav = useNavigate();
  const { data: me } = useMe();
  const [params] = useSearchParams();
  const [tab, setTab] = useState<"paste" | "upload">("paste");
  const [title, setTitle] = useState("");
  const [channel, setChannel] = useState<Channel>("instagram");
  const [purpose, setPurpose] = useState("");
  const [text, setText] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const sample = useQuery({ queryKey: ["sample"], queryFn: () => api.get<Sample>("/api/demo/sample"), enabled: !!me?.org.is_sandbox });

  const loadSample = () => {
    if (!sample.data) return;
    setTab("paste");
    setTitle(sample.data.title);
    setChannel(sample.data.channel);
    setPurpose(sample.data.purpose);
    setText(sample.data.text);
  };
  useEffect(() => {
    if (params.get("sample") && sample.data && !text) loadSample();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sample.data]);

  const submit = useMutation({
    mutationFn: async () => {
      if (tab === "upload") {
        const file = fileRef.current?.files?.[0];
        if (!file) throw new Error("Choose a .docx or .pdf file");
        const fd = new FormData();
        fd.append("title", title);
        fd.append("channel", channel);
        fd.append("purpose", purpose);
        fd.append("file", file);
        return api.post<{ id: string }>("/api/drafts/upload", fd);
      }
      return api.post<{ id: string }>("/api/drafts", { title, channel, purpose, text });
    },
    onSuccess: (d) => {
      markStep(me?.org.slug, "submitted");
      nav(`/drafts/${d.id}`);
    },
  });

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h1 className="page-title">New draft</h1>
        {me?.org.is_sandbox && (
          <Button onClick={loadSample} disabled={!sample.data}>
            <Sparkles className="h-4 w-4" /> Load sample caption
          </Button>
        )}
      </div>
      <Card className="p-4 sm:p-6">
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); submit.mutate(); }}>
          <div className="grid gap-4 sm:grid-cols-[1fr_200px]">
            <label className="block text-sm">
              <span className="font-medium">Title</span>
              <input required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)}
                className="field" placeholder="AloeCalm launch caption" />
            </label>
            <label className="block text-sm">
              <span className="font-medium">Channel</span>
              <select value={channel} onChange={(e) => setChannel(e.target.value as Channel)}
                className="field">
                {Object.entries(CHANNEL_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
          </div>
          <label className="block text-sm">
            <span className="font-medium">Purpose line</span>
            <span className="mt-0.5 block text-ink-faint sm:ml-2 sm:mt-0 sm:inline">What should this copy achieve? Fixes are checked against it.</span>
            <input required minLength={3} maxLength={140} value={purpose} onChange={(e) => setPurpose(e.target.value)}
              className="field" placeholder="Announce the AloeCalm launch to followers" />
            <span className="mt-1 block text-right text-xs text-ink-faint">{purpose.length}/140</span>
          </label>

          <div role="tablist" className="flex gap-1 border-b border-line">
            {(["paste", "upload"] as const).map((t) => (
              <button type="button" key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                className={clsx("-mb-px border-b-2 px-3 py-2 text-sm capitalize",
                  tab === t ? "border-brand-500 font-medium text-ink" : "border-transparent text-ink-soft hover:text-ink")}>
                {t === "paste" ? "Paste text" : "Upload DOCX / PDF"}
              </button>
            ))}
          </div>
          {tab === "paste" ? (
            <label className="block text-sm">
              <span className="sr-only">Draft text</span>
              <textarea required rows={8} value={text} onChange={(e) => setText(e.target.value)}
                className="field mt-0 p-3 text-[15px] leading-7"
                placeholder="Paste your caption, email or product copy…" />
            </label>
          ) : (
            <label className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed border-slate-300 bg-canvas px-4 py-8 text-center text-sm text-ink-soft hover:border-brand-500">
              <Upload className="h-5 w-5" />
              <span>.docx or .pdf, up to 5 MB. Text is extracted; images are not checked yet.</span>
              <input ref={fileRef} type="file" accept=".docx,.pdf" className="text-sm" />
            </label>
          )}
          <ErrorNote error={submit.error} />
          <div className="flex justify-end">
            <Button type="submit" variant="primary" busy={submit.isPending}>Check this draft</Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
