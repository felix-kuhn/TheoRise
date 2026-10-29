// Compatibility layer: the live client lives in src/api/client.js.

import { apiGet, apiPost, BackendError, getHealth } from "@/api/client";

export { BackendError, getHealth };

export const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8766";

export const listTheories = () => apiGet("/v1/theories");

export const getTheory = (slug) => apiGet(`/v1/theories/${encodeURIComponent(slug)}`);

export const startHydration = () => apiPost("/v1/theories/hydrate");

export const getJob = (jobId) => apiGet(`/v1/theories/jobs/${encodeURIComponent(jobId)}`);
