// HTTP client for the authenticated local backend.
//
// Inside Tauri the backend URL and token come from the Rust shell
// (`get_backend_info`). In a plain browser/Vite session it falls back to
// VITE_BACKEND_URL / VITE_BACKEND_TOKEN.

import { invoke } from "@tauri-apps/api/core";

const FALLBACK_BASE_URL = (
  import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8766"
).replace(/\/+$/, "");

let backendInfoPromise;

export function isTauri() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function getBackendInfo() {
  if (isTauri()) {
    backendInfoPromise ??= (async () => {
      await invoke("start_backend");
      const info = await invoke("get_backend_info");
      return {
        baseUrl: String(info.baseUrl).replace(/\/+$/, ""),
        token: String(info.token ?? ""),
      };
    })();
    return backendInfoPromise;
  }

  return {
    baseUrl: FALLBACK_BASE_URL,
    token: import.meta.env.VITE_BACKEND_TOKEN ?? "",
  };
}

export class BackendError extends Error {
  constructor(
    message,
    { code = "backend_error", details = {}, status = null, reachable = true } = {},
  ) {
    super(message);
    this.name = "BackendError";
    this.code = code;
    this.details = details;
    this.status = status;
    this.reachable = reachable;
  }
}

async function fetchBackend(path, options = {}) {
  const info = await getBackendInfo();
  const headers = new Headers(options.headers ?? {});

  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  if (options.body != null && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (info.token) {
    headers.set("Authorization", `Bearer ${info.token}`);
  }

  const fetchImpl = isTauri()
    ? (await import("@tauri-apps/plugin-http")).fetch
    : globalThis.fetch;

  return fetchImpl(`${info.baseUrl}${path}`, {
    ...options,
    headers,
  });
}

async function parseResponse(response) {
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    const code = body?.code ?? body?.detail?.code ?? `http_${response.status}`;
    const message =
      body?.message ??
      body?.detail?.message ??
      body?.detail?.reason ??
      response.statusText;
    const details =
      body?.details ??
      (body?.detail && typeof body.detail === "object" ? body.detail : {});

    throw new BackendError(message, {
      code,
      details,
      status: response.status,
    });
  }

  return body;
}

export async function apiRequest(path, options = {}) {
  let response;
  try {
    response = await fetchBackend(path, options);
  } catch (error) {
    if (error instanceof BackendError) {
      throw error;
    }
    throw new BackendError("Backend is not reachable", {
      code: "backend_unreachable",
      details: { cause: error instanceof Error ? error.message : String(error) },
      reachable: false,
    });
  }
  return parseResponse(response);
}

export const apiGet = (path, options = {}) =>
  apiRequest(path, { method: "GET", ...options });

export const apiPost = (path, body, options = {}) =>
  apiRequest(path, {
    method: "POST",
    body: body == null ? undefined : JSON.stringify(body),
    ...options,
  });

export const getHealth = () => apiGet("/api/health");

export async function streamSse(path, { onEvent, signal } = {}) {
  let response;
  try {
    response = await fetchBackend(path, {
      method: "GET",
      headers: { Accept: "text/event-stream" },
      signal,
    });
  } catch (error) {
    if (error instanceof BackendError) {
      throw error;
    }
    throw new BackendError("Backend is not reachable", {
      code: "backend_unreachable",
      details: { cause: error instanceof Error ? error.message : String(error) },
      reachable: false,
    });
  }

  if (!response.ok) {
    await parseResponse(response);
  }
  if (!response.body) {
    throw new BackendError("Streaming is not supported", {
      code: "streaming_unsupported",
    });
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      let eventName = "message";
      let data = "";

      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          data += `${line.slice(5).trimStart()}\n`;
        }
      }

      if (data) {
        onEvent?.(eventName, data.trimEnd());
      }
    }
  }
}
