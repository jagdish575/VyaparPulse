export type StockStatus = "in_stock" | "low_stock" | "out_of_stock";

export interface Product {
  id: number;
  name: string;
  brand: string;
  category: string;
  unit: string;
  price: number;
  stock_quantity: number;
  low_stock_threshold: number;
  description: string;
  aliases: string;
  is_active: boolean;
  stock_status: StockStatus;
  created_at: string;
  updated_at: string;
}

export interface InventoryLog {
  id: number;
  product_id: number;
  product_name: string;
  order_id: number | null;
  change_type: string;
  quantity_change: number;
  stock_before: number;
  stock_after: number;
  created_at: string;
}

export interface ProductDetail extends Product {
  logs: InventoryLog[];
}

export interface InventoryResponse {
  summary: {
    total_products: number;
    in_stock: number;
    low_stock: number;
    out_of_stock: number;
    total_units: number;
    stock_value: number;
  };
  categories: string[];
  products: Product[];
}

export interface Customer {
  id: number;
  name: string;
  phone: string;
  address: string;
  created_at: string;
}

export interface CustomerSummary extends Customer {
  orders_count: number;
  total_spent: number;
  last_order_at: string | null;
}

export interface OrderItem {
  id: number;
  product_id: number;
  product_name: string;
  product_unit: string;
  quantity: number;
  unit_price: number;
  line_total: number;
}

export interface Order {
  id: number;
  customer_id: number;
  customer_name: string;
  status: string;
  subtotal: number;
  delivery_charge: number;
  total: number;
  delivery_address: string;
  source: string;
  original_request: string | null;
  item_count: number;
  items: OrderItem[];
  created_at: string;
}

export interface Activity {
  id: number;
  order_id: number | null;
  action: string;
  status: string;
  message: string;
  created_at: string;
}

export interface OrderDetail extends Order {
  customer: Customer;
  activity: Activity[];
  inventory_changes: InventoryLog[];
}

export interface CustomerDetail extends CustomerSummary {
  average_order_value: number;
  orders: Order[];
  recent_activity: Activity[];
}

export interface DashboardStats {
  orders_today: number;
  revenue_today: number;
  items_sold_today: number;
  orders_trend_pct: number | null;
  revenue_trend_pct: number | null;
  items_trend_pct: number | null;
  yesterday: { orders: number; revenue: number; items: number };
  low_stock_count: number;
  out_of_stock_count: number;
  total_products: number;
  stock_value: number;
  total_orders: number;
  total_revenue: number;
  pending_orders: number;
  ai_handled_orders: number;
  daily: { date: string; orders: number; revenue: number }[];
  top_products: { product_id: number; name: string; quantity: number }[];
}

export interface SettingsInfo {
  store: { name: string; location: string; delivery_charge: number; free_delivery_above: number };
  ai: { provider: string; model: string; configured: boolean };
  demo_mode: boolean;
  database: { engine: string; products: number; customers: number; orders: number };
}

export interface AiStatus {
  provider: string;
  model: string;
  base_url: string;
  configured: boolean;
  connected: boolean | null;
  error: string | null;
}

// ---- agent ----

export type StepStatus = "completed" | "failed" | "needs_input" | "skipped";

export interface AgentStep {
  name: string;
  title: string;
  status: StepStatus;
  message: string;
  timestamp: string | null;
  duration_ms: number | null;
  tools: string[];
}

export interface ClarificationOption {
  product_id: number;
  name: string;
  price: number;
  unit: string;
  stock_quantity: number;
  stock_status: StockStatus;
}

export interface ProductCard {
  id: number;
  name: string;
  brand: string;
  category: string;
  unit: string;
  price: number;
  stock_quantity: number;
  stock_status: StockStatus;
}

export interface DraftItem {
  query: string;
  quantity: number;
  category_hint: string | null;
  product_id: number | null;
  option_ids: number[];
}

export interface Draft {
  items: DraftItem[];
  delivery: boolean | null;
  delivery_address: string | null;
  original_request: string | null;
}

export interface AgentOrder extends Order {
  customer: Customer;
  inventory_changes: InventoryLog[];
}

export interface AgentResponse {
  success: boolean;
  intent: string;
  status: "confirmed" | "needs_clarification" | "needs_input" | "rejected" | "info" | "error";
  steps: AgentStep[];
  order: AgentOrder | null;
  message: string;
  reply: string;
  clarification: { question: string; item_query: string; options: ClarificationOption[] } | null;
  draft: Draft | null;
  products: ProductCard[];
  parser: { provider: "euri" | "local"; model: string | null; note: string | null } | null;
  inventory_updates: InventoryLog[];
}
