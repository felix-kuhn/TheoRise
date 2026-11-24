import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Settings from "./Settings";

vi.mock("@/api/llm", () => ({
  getConfig: vi.fn(),
  getNetworkStatus: vi.fn(),
  listModels: vi.fn(),
  saveConfig: vi.fn(),
  testConfig: vi.fn(),
}));

import {
  getConfig,
  getNetworkStatus,
  listModels,
  saveConfig,
  testConfig,
} from "@/api/llm";

function makeConfig() {
  return {
    chat: {
      base_url: "http://127.0.0.1:8000/v1",
      model: "chat-model",
      api_key_set: true,
      system_instructions: "",
      temperature: 0,
      max_tokens: null,
      timeout_s: 120,
      extra_headers: {},
      extra_body: {},
      supports_json_schema: null,
    },
    extraction: {
      base_url: "http://127.0.0.1:8000/v1",
      model: "extract-model",
      api_key_set: false,
      system_instructions: "",
      temperature: 0,
      max_tokens: null,
      timeout_s: 120,
      extra_headers: {},
      extra_body: {},
      supports_json_schema: null,
    },
    linking: {
      base_url: "http://127.0.0.1:8000/v1",
      model: "link-model",
      api_key_set: false,
      system_instructions: "",
      temperature: 0,
      max_tokens: null,
      timeout_s: 120,
      extra_headers: {},
      extra_body: {},
      supports_json_schema: null,
    },
    embedding: {
      base_url: "http://127.0.0.1:8000/v1",
      model: "embed-model",
      api_key_set: false,
      system_instructions: "",
      temperature: 0,
      max_tokens: null,
      timeout_s: 120,
      extra_headers: {},
      extra_body: {},
      supports_json_schema: null,
      dimensions: null,
      query_prefix: "",
      document_prefix: "",
      batch_size: 32,
    },
    rerank: {
      mode: "none",
      base_url: "http://127.0.0.1:8000/v1",
      model: "rerank-model",
      api_key_set: false,
      top_n: 10,
    },
    concurrency: 4,
    token_budget_per_job: null,
    keychain: { available: false, warning: "" },
  };
}

function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <Settings />
    </QueryClientProvider>,
  );
}

describe("Settings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();

    getConfig.mockResolvedValue(makeConfig());
    getNetworkStatus.mockResolvedValue({
      roles: [
        {
          role: "chat",
          base_url: "http://127.0.0.1:8000/v1",
          host: "127.0.0.1",
          local: true,
        },
      ],
    });
    listModels.mockResolvedValue({ models: [] });
    saveConfig.mockImplementation(async () => makeConfig());
    testConfig.mockResolvedValue({
      role: "chat",
      ok: true,
      latency_ms: 12,
      error: null,
      detected: { supports_json_schema: true },
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("loads config and masks the saved API key", async () => {
    renderSettings();

    expect(await screen.findByDisplayValue("chat-model")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Saved key")).toHaveValue("");
    expect(screen.queryByDisplayValue("sk-test-secret")).not.toBeInTheDocument();
    expect(localStorage.getItem("research-assistant-store")).toBeNull();
  });

  it("saves without sending the existing API key", async () => {
    renderSettings();

    const modelInput = await screen.findByDisplayValue("chat-model");
    fireEvent.change(modelInput, { target: { value: "chat-v2" } });

    fireEvent.click(screen.getByRole("button", { name: /Save/ }));

    await waitFor(() => expect(saveConfig).toHaveBeenCalledTimes(1));
    const payload = saveConfig.mock.calls[0][0];
    expect(payload.chat.model).toBe("chat-v2");
    expect(payload.chat.api_key).toBeUndefined();
    expect(JSON.stringify(payload)).not.toContain("sk-test-secret");
  });

  it("shows the connection test result", async () => {
    renderSettings();

    await screen.findByDisplayValue("chat-model");
    fireEvent.click(screen.getByRole("button", { name: /Test connection/ }));

    expect(await screen.findByText(/Connection OK · 12 ms/)).toBeInTheDocument();
    expect(testConfig).toHaveBeenCalledWith("chat");
  });
});
