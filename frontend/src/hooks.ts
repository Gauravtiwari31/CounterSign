import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
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

/** Clears every cached query after sign-in or sign-out. */
export function useResetSession() {
  const qc = useQueryClient();
  return useCallback(() => qc.resetQueries(), [qc]);
}
