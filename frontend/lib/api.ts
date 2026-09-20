import type {
  Activity,
  AgentResponse,
  AiStatus,
  CustomerDetail,
  CustomerSummary,
  DashboardStats,
  Draft,
  InventoryResponse,
  Order,
  OrderDetail,
  ProductDetail,
  SettingsInfo,
} from "@/types";

/** Fired when the API answers 401 (session expired / signed out) so the app can show the login screen. */
export const UNAUTHORIZED_EVENT = "kirai:unauthorized";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

/** An error that is always safe to show to a user. Raw backend/network errors are never exposed. */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status = 0) {
    super(message);
    this.status = status;
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
      cache: "no-store",
      credentials: "include", // the owner session lives in an HttpOnly cookie set by the API
    });
  } catch {
    throw new ApiError("We couldn't reach the KirAI server. Check that the backend is running and try again.");
  }
  if (!res.ok) {
    if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/api/auth/")) {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    let message = "Something went wrong. Please try again.";
    try {
      const body = await res.json();
      if (body?.detail?.message) message = body.detail.message;
    } catch {
      /* keep generic message */
    }
    throw new ApiError(message, res.status);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string; database: string; ai_configured: boolean }>("/api/health"),
  dashboard: () => request<DashboardStats>("/api/dashboard/stats"),
  inventory: () => request<InventoryResponse>("/api/inventory"),
  product: (id: number) => request<ProductDetail>(`/api/products/${id}`),
  orders: (limit = 200) => request<Order[]>(`/api/orders?limit=${limit}`),
  order: (id: number) => request<OrderDetail>(`/api/orders/${id}`),
  setOrderStatus: (id: number, status: "out_for_delivery" | "delivered") =>
    request<Order>(`/api/orders/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) }),
  customers: () => request<CustomerSummary[]>("/api/customers"),
  customer: (id: number) => request<CustomerDetail>(`/api/customers/${id}`),
  activity: (limit = 80) => request<Activity[]>(`/api/activity?limit=${limit}`),
  settings: () => request<SettingsInfo>("/api/settings"),
  aiStatus: (check = false) => request<AiStatus>(`/api/ai/status${check ? "?check=true" : ""}`),
  resetDemo: () =>
    request<{ success: boolean; message: string; products: number; orders: number }>("/api/demo/reset", { method: "POST" }),
  /** `key` makes a retry safe: the same key + request never creates a second order or deducts stock twice. */
  process: (body: { message: string; customer_id?: number; delivery_address?: string; draft?: Draft | null }, key?: string) =>
    request<AgentResponse>("/api/agent/process", {
      method: "POST",
      headers: key ? { "Idempotency-Key": key } : undefined,
      body: JSON.stringify(body),
    }),
};

export interface AuthStatus {
  mode: "required" | "open" | "unconfigured";
  auth_required: boolean;
  authenticated: boolean;
}

export const authApi = {
  me: () => request<AuthStatus>("/api/auth/me"),
  login: (password: string) =>
    request<{ authenticated: boolean }>("/api/auth/login", { method: "POST", body: JSON.stringify({ password }) }),
  logout: () => request<{ authenticated: boolean }>("/api/auth/logout", { method: "POST" }),
};

/** New random key for one user action (safe to reuse only when retrying that exact same action). */
export function newRequestKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `k${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
}

/** Unfinished forms are kept locally across reloads; sign-out removes them (they may hold customer/financial details). */
export function clearLocalDrafts() {
  try {
    Object.keys(localStorage)
      .filter((k) => k.startsWith("vyaparpulse:") || k.startsWith("kirai:"))
      .forEach((k) => localStorage.removeItem(k));
  } catch {
    /* storage unavailable */
  }
}
