import { CheckCircle2, LoaderCircle, WifiOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { useBackendHealth } from "@/hooks/use-backend-health";

export function BackendStatus() {
  const { data, error, isLoading } = useBackendHealth();

  let label = "Backend connecting…";
  let variant = "outline";
  let Icon = LoaderCircle;

  if (error || (data && data.status !== "ok")) {
    label = "Backend error";
    variant = "destructive";
    Icon = WifiOff;
  } else if (data?.status === "ok") {
    label = "Backend OK";
    variant = "default";
    Icon = CheckCircle2;
  }

  return (
    <Badge data-testid="backend-status" variant={variant}>
      <Icon className={isLoading ? "animate-spin" : undefined} aria-hidden="true" />
      {label}
    </Badge>
  );
}
