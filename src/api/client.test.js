import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiGet, getHealth } from "./client";

function mockFetchResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("api client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("attaches the bearer token to requests", async () => {
    globalThis.fetch.mockResolvedValue(mockFetchResponse({ status: "ok" }));

    await apiGet("/api/health");

    const [url, options] = globalThis.fetch.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:9999/api/health");
    expect(options.headers.get("Authorization")).toBe("Bearer test-token");
    expect(options.headers.get("Accept")).toBe("application/json");
  });

  it("surfaces backend errors with code and status", async () => {
    globalThis.fetch.mockResolvedValue(
      mockFetchResponse(
        { code: "unauthorized", message: "Missing or invalid bearer token" },
        401,
      ),
    );

    await expect(getHealth()).rejects.toMatchObject({
      code: "unauthorized",
      status: 401,
      message: "Missing or invalid bearer token",
    });
  });

  it("wraps network failures as unreachable", async () => {
    globalThis.fetch.mockRejectedValue(new TypeError("fetch failed"));

    await expect(getHealth()).rejects.toMatchObject({
      code: "backend_unreachable",
      reachable: false,
    });
  });
});
