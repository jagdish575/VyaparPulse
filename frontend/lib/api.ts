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
    });
  } catch {
    throw new ApiError("We couldn't reach the KirAI server. Check that the backend is running and try again.");
  }
  if (!res.ok) {
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
  process: (body: { message: string; customer_id?: number; delivery_address?: string; draft?: Draft | null }) =>
    request<AgentResponse>("/api/agent/process", { method: "POST", body: JSON.stringify(body) }),
};
