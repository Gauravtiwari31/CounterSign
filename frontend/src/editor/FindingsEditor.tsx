/**
 * TipTap editor whose findings are ProseMirror decorations. Decorations are mapped through every transaction
 * (DecorationSet.map), so highlights stay on the right words while the creator edits. Accepting a fix is a
 * transaction that replaces the decoration's current range.
 */
import { Extension } from "@tiptap/core";
import { Plugin, PluginKey, type EditorState } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import { EditorContent, useEditor } from "@tiptap/react";
import Document from "@tiptap/extension-document";
import History from "@tiptap/extension-history";
import Paragraph from "@tiptap/extension-paragraph";
import Text from "@tiptap/extension-text";
import clsx from "clsx";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import { cpToUtf16 } from "../api/client";
import type { Finding } from "../api/types";
import { laneBadge } from "../components/ui";

const key = new PluginKey<DecorationSet>("findings");
const CLOSED = new Set(["dismissed", "overridden", "resolved"]);

interface Spec { id: string; kind: "inline" | "badge" }

function makeExtension(onSelect: { current: (id: string) => void }) {
  return Extension.create({
    name: "findingsHighlight",
    addProseMirrorPlugins() {
      return [new Plugin<DecorationSet>({
        key,
        state: {
          init: () => DecorationSet.empty,
          apply: (tr, old) => tr.getMeta(key) ?? old.map(tr.mapping, tr.doc),
        },
        props: {
          decorations: (state) => key.getState(state),
          handleClick: (view, pos) => {
            const hit = key.getState(view.state)?.find(pos, pos, (s: Spec) => s.kind === "inline")[0];
            if (hit) onSelect.current((hit.spec as Spec).id);
            return false;
          },
        },
      })];
    },
  });
}

function textToDoc(text: string) {
  return {
    type: "doc",
    content: text.split("\n").map((line) => ({ type: "paragraph", content: line ? [{ type: "text", text: line }] : [] })),
  };
}

export function docText(state: EditorState): string {
  const lines: string[] = [];
  state.doc.forEach((node) => lines.push(node.textContent));
  return lines.join("\n");
}

/** Map a UTF-16 offset in the version text to a ProseMirror position (one paragraph per line). */
function offsetToPos(state: EditorState, text: string, offset: number): number {
  const starts: number[] = [];
  state.doc.forEach((_node, pos) => starts.push(pos + 1));
  let lineStart = 0;
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const lineEnd = lineStart + lines[i].length;
    if (offset <= lineEnd || i === lines.length - 1) return starts[i] + Math.min(offset - lineStart, lines[i].length);
    lineStart = lineEnd + 1;
  }
  return 1;
}

function decorationsFor(f: Finding, from: number, to: number, active: boolean): Decoration[] {
  const b = laneBadge(f);
  const closed = CLOSED.has(f.status);
  const inline = Decoration.inline(from, to, {
    class: clsx("hl", closed ? "hl-closed" : `hl-${b.cls}`, active && "hl-active"),
    "data-finding": f.id,
    title: `${b.text}: ${f.message}`,
  }, { id: f.id, kind: "inline" } satisfies Spec);
  const badge = Decoration.widget(to, () => {
    const el = document.createElement("span");
    el.className = `hl-badge hl-badge-${b.cls}`;
    el.textContent = b.text;
    el.setAttribute("aria-hidden", "true");
    el.dataset.finding = f.id;
    return el;
  }, { id: f.id, kind: "badge", side: 1, ignoreSelection: true, key: `${f.id}:${b.cls}:${active}` });
  return [inline, badge];
}

export interface EditorHandle {
  getText: () => string;
  applyFix: (id: string, replacement: string) => boolean;
  focusFinding: (id: string) => void;
  hasRange: (id: string) => boolean;
}

interface Props {
  versionId: string;
  text: string;
  findings: Finding[];
  editable: boolean;
  activeId: string | null;
  onSelect: (id: string) => void;
  onDirtyChange: (dirty: boolean) => void;
}

export const FindingsEditor = forwardRef<EditorHandle, Props>(function FindingsEditor(
  { versionId, text, findings, editable, activeId, onSelect, onDirtyChange }, ref) {
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;
  const dirtyRef = useRef(onDirtyChange);
  dirtyRef.current = onDirtyChange;
  const textRef = useRef(text);
  textRef.current = text;

  const editor = useEditor({
    extensions: [
      Document, Paragraph, Text, History,
      makeExtension(selectRef),
    ],
    content: textToDoc(text),
    editable,
    editorProps: { attributes: { "aria-label": "Draft text", spellcheck: "true" } },
    onUpdate: ({ editor }) => dirtyRef.current(docText(editor.state) !== textRef.current),
  });

  // new version: reset content and rebuild decorations from backend offsets
  const builtFor = useRef<string | null>(null);
  const idsKey = findings.map((f) => f.id).join(",");
  useEffect(() => {
    if (!editor) return;
    const rebuild = builtFor.current !== `${versionId}|${idsKey}`;
    if (rebuild) {
      if (builtFor.current?.split("|")[0] !== versionId || docText(editor.state) !== text) {
        editor.commands.setContent(textToDoc(text), false);
        dirtyRef.current(false);
      }
      const decos = findings.flatMap((f) => {
        const from = offsetToPos(editor.state, text, cpToUtf16(text, f.span.start));
        const to = offsetToPos(editor.state, text, cpToUtf16(text, f.span.end));
        return to > from ? decorationsFor(f, from, to, f.id === activeId) : [];
      });
      editor.view.dispatch(editor.state.tr.setMeta(key, DecorationSet.create(editor.state.doc, decos)).setMeta("addToHistory", false));
      builtFor.current = `${versionId}|${idsKey}`;
      return;
    }
    // same findings, new statuses or active item: restyle at the *mapped* positions
    const set = key.getState(editor.state);
    if (!set) return;
    const byId = new Map(findings.map((f) => [f.id, f]));
    const decos = set.find(undefined, undefined, (s: Spec) => s.kind === "inline").flatMap((d) => {
      const f = byId.get((d.spec as Spec).id);
      return f && f.status !== "accepted" ? decorationsFor(f, d.from, d.to, f.id === activeId) : [];
    });
    editor.view.dispatch(editor.state.tr.setMeta(key, DecorationSet.create(editor.state.doc, decos)).setMeta("addToHistory", false));
  }, [editor, versionId, idsKey, findings, text, activeId]);

  useEffect(() => { editor?.setEditable(editable); }, [editor, editable]);

  useImperativeHandle(ref, () => ({
    getText: () => (editor ? docText(editor.state) : text),
    hasRange: (id) => !!editor && !!key.getState(editor.state)?.find(undefined, undefined, (s: Spec) => s.id === id && s.kind === "inline").length,
    applyFix: (id, replacement) => {
      if (!editor) return false;
      const set = key.getState(editor.state);
      const hit = set?.find(undefined, undefined, (s: Spec) => s.id === id && s.kind === "inline")[0];
      if (!set || !hit) return false;
      const tr = editor.state.tr.insertText(replacement, hit.from, hit.to);
      editor.view.dispatch(tr);
      const after = key.getState(editor.state)!;
      const remove = after.find(undefined, undefined, (s: Spec) => s.id === id);
      editor.view.dispatch(editor.state.tr.setMeta(key, after.remove(remove)).setMeta("addToHistory", false));
      return true;
    },
    focusFinding: (id) => {
      const el = editor?.view.dom.querySelector(`[data-finding="${id}"]`);
      el?.scrollIntoView({ block: "center", behavior: "smooth" });
    },
  }), [editor, text]);

  return <EditorContent editor={editor} className={clsx("cs-editor", !editable && "cursor-default")} />;
});
