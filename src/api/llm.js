import { apiGet, apiPost, apiPut } from "./client";

export function getConfig() {
  return apiGet("/api/config");
}

export function saveConfig(payload) {
  return apiPut("/api/config", payload);
}

export function testConfig(role) {
  return apiPost("/api/config/test", { role });
}

export function listModels(role) {
  return apiGet(`/api/config/models?role=${encodeURIComponent(role)}`);
}

export function getNetworkStatus() {
  return apiGet("/api/config/network-status");
}

export function sendChat(messages) {
  return apiPost("/api/chat", { messages, role: "chat" });
}
