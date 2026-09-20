import { request } from "@/lib/api";

export interface Invoice {
  id: number;
  customer_id: number;
  customer_name: string;
  order_id: number | null;
  description: string;
  kind: "sale" | "opening_receivable";
  total_paise: number;
  received_paise: number;
  outstanding_paise: number;
  due_date: string | null;
  status: "paid" | "overdue" | "upcoming";
  created_at: string;
}

export interface Payable {
  id: number;
  supplier: string;
  description: string;
  total_paise: number;
  paid_paise: number;
  outstanding_paise: number;
  due_date: string;
  status: "paid" | "overdue" | "upcoming";
}

export interface LedgerSummary {
  configured: boolean;
  started_at: string | null;
  opening_paise: number | null;
  available_paise: number | null;
  sales_paise: number;
  receivables_paise: number;
  overdue_paise: number;
  upcoming_paise: number;
  supplier_due_paise: number;
  shortfall_paise: number | null;
  horizon_days: number;
  through_date: string;
  priorities: Invoice[];
  unrecorded_orders: number;
}

export interface LedgerEntry {
  id: string;
  invoice_id: number;
  kind: string;
  description: string;
  amount_paise: number;
  balance_paise: number;
  created_at: string;
}

export interface Movement {
  id: number;
  kind: string;
  description: string;
  method: string;
  amount_paise: number;
  created_at: string;
}

export const ledgerApi = {
  summary: () => request<LedgerSummary>("/api/ledger/summary"),
  invoices: (customer: string, offset: number) => request<{ total: number; entries: Invoice[] }>(`/api/ledger/invoices?offset=${offset}${customer ? `&customer_id=${customer}` : ""}`),
  payables: (offset: number) => request<{ total: number; entries: Payable[] }>(`/api/ledger/payables?offset=${offset}`),
  movements: (offset: number) => request<{ total: number; entries: Movement[] }>(`/api/ledger/movements?offset=${offset}`),
  customer: (id: string, offset: number) => request<{ customer_name: string; balance_paise: number; total: number; entries: LedgerEntry[] }>(`/api/ledger/customers/${id}?offset=${offset}`),
  reminder: (id: number) => request<{ text: string }>(`/api/ledger/invoices/${id}/reminder`),
  save: (path: string, body: Record<string, unknown>, key: string) => request<unknown>(`/api/ledger${path}`, {
    method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify(body),
  }),
};

export function funds(paise: number | null | undefined): string {
  if (paise == null) return "Not set";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2 }).format(paise / 100);
}
