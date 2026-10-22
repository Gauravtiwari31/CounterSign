import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api/client";
import type { Me } from "./api/types";

export function useMe() {
  return useQuery<Me | null>({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api.get<Me>("/api/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
  });
}

/** Clears every cached query after a role switch or new session. */
export function useResetSession() {
  const qc = useQueryClient();
  return useCallback(() => qc.resetQueries(), [qc]);
}

// ---- guided checklist for first-time visitors (judges) ----

export const CHECKLIST = [
  { key: "submitted", label: "Load the Round 1 example and check it" },
  { key: "findings", label: "Read the findings (rules, claims, voice)" },
  { key: "fixed", label: "Accept a fix and re-check" },
  { key: "sent", label: "Send for countersign" },
  { key: "approved", label: "Switch to Reviewer and approve" },
  { key: "history", label: "Open History: decisions and audit chain" },
] as const;
export type StepKey = (typeof CHECKLIST)[number]["key"];

const EVENT = "cs-checklist";

function storageKey(org?: string) {
  return `cs-checklist:${org ?? "anon"}`;
}

function read(org?: string): StepKey[] {
  try {
    return JSON.parse(localStorage.getItem(storageKey(org)) ?? "[]");
  } catch {
    return [];
  }
}

export function markStep(org: string | undefined, step: StepKey) {
  const done = read(org);
  if (done.includes(step)) return;
  try {
    localStorage.setItem(storageKey(org), JSON.stringify([...done, step]));
  } catch { /* storage unavailable: checklist simply doesn't persist */ }
  window.dispatchEvent(new Event(EVENT));
}

export function useChecklist(org?: string) {
  const [done, setDone] = useState<StepKey[]>(() => read(org));
  useEffect(() => {
    const sync = () => setDone(read(org));
    sync();
    window.addEventListener(EVENT, sync);
    return () => window.removeEventListener(EVENT, sync);
  }, [org]);
  return done;
}
