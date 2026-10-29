import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getHealth } from "@/api/client";
import { BackendStatus } from "@/components/backend-status";

vi.mock("@/api/client", () => ({
  getHealth: vi.fn(),
}));

function renderStatus() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <BackendStatus />
    </QueryClientProvider>,
  );
}

describe("BackendStatus", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the OK state when health returns ok", async () => {
    getHealth.mockResolvedValue({ status: "ok", version: "0.1.0" });

    renderStatus();

    expect(await screen.findByText("Backend OK")).toBeInTheDocument();
  });

  it("renders the error state when the backend is unreachable", async () => {
    getHealth.mockRejectedValue(new Error("Backend is not reachable"));

    renderStatus();

    expect(await screen.findByText("Backend error")).toBeInTheDocument();
  });
});
