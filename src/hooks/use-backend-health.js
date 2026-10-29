import { useQuery } from "@tanstack/react-query";

import { getHealth } from "@/api/client";

export function useBackendHealth() {
  return useQuery({
    queryKey: ["backend-health"],
    queryFn: getHealth,
    staleTime: 10_000,
    refetchInterval: 15_000,
    retry: false,
  });
}
