import type {
  AgentResponse,
  Anomaly,
  Cost,
  DataQuality,
  Experience,
  Overview,
  Safety,
  ShiftReadiness,
  VendorAnalysis,
  VendorResult,
} from './types';

const BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const REQUEST_TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string) {
    super(message);
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
      signal: options?.signal ?? controller.signal,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new ApiError(
        response.status,
        body.detail || `Request failed (${response.status})`,
        body.error,
      );
    }
    return response.json() as Promise<T>;
  } catch (error) {
    if (controller.signal.aborted) {
      throw new ApiError(
        504,
        'Pulse analysis timed out. Deterministic dashboards remain available; retry the request.',
        'request_timeout',
      );
    }
    if (error instanceof TypeError) {
      throw new ApiError(
        0,
        'The backend is unavailable. Start the API and retry.',
        'backend_unavailable',
      );
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

const query = (values: Record<string, string | undefined>) =>
  new URLSearchParams(
    Object.entries(values).filter((entry): entry is [string, string] => Boolean(entry[1])),
  ).toString();

export const api = {
  overview: (month: string) => request<Overview>(`/api/overview?${query({ month })}`),
  anomalies: (month: string, limit = '50') =>
    request<Anomaly[]>(`/api/anomalies?${query({ month, limit })}`),
  vendors: (month: string, baseline_month: string) =>
    request<VendorAnalysis>(`/api/vendors?${query({ month, baseline_month })}`),
  vendor: (name: string, month: string, baseline_month: string) =>
    request<VendorResult>(
      `/api/vendors/${encodeURIComponent(name)}?${query({ month, baseline_month })}`,
    ),
  shifts: (month: string) =>
    request<ShiftReadiness>(`/api/shifts/readiness?${query({ month })}`),
  safety: (month: string, vendor?: string, office?: string) =>
    request<Safety>(`/api/safety?${query({ month, vendor, office })}`),
  cost: (month: string, vendor?: string) =>
    request<Cost>(`/api/cost?${query({ month, vendor })}`),
  experience: (month: string, vendor?: string) =>
    request<Experience>(`/api/experience?${query({ month, vendor })}`),
  quality: () => request<DataQuality>('/api/data-quality'),
  queryAgent: (question: string, month: string, baseline_month: string) =>
    request<AgentResponse>('/api/agent/query', {
      method: 'POST',
      body: JSON.stringify({ question, month, baseline_month }),
    }),
  investigate: (anomaly_id: string, month: string) =>
    request<AgentResponse>('/api/agent/investigate', {
      method: 'POST',
      body: JSON.stringify({ anomaly_id, month }),
    }),
  executive: (month: string, baseline_month: string) =>
    request<AgentResponse>('/api/reports/executive-summary', {
      method: 'POST',
      body: JSON.stringify({ month, baseline_month }),
    }),
};
