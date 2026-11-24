import { useQuery } from "@tanstack/react-query";

import { getConfig } from "@/api/llm";

export function useRuntimeConfig() {
  return useQuery({
    queryKey: ["runtime-config"],
    queryFn: getConfig,
    retry: false,
  });
}
