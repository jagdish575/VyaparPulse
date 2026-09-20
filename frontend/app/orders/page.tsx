"use client";

import { Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { BadgeIndianRupee, Clock, RefreshCw, Search, ShoppingBag, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/hooks/use-api";
import { dateTime, inr, timeAgo } from "@/lib/format";
import { Card, EmptyState, ErrorState, OrderStatusBadge, PageHeader, RowsSkeleton, SourceBadge, StatCard } from "@/components/shared";
import { OrderDrawer } from "@/components/orders/order-drawer";
import { Button } from "@/components/ui/button";
import type { Order } from "@/types";

export default function OrdersPage() {
  return (
    <Suspense fallback={<RowsSkeleton rows={6} label="Loading orders..." />}>
      <OrdersView />
    </Suspense>
  );
}

function OrdersView() {
  const router = useRouter();
  const params = useSearchParams();
  const openId = params.get("open") ? Number(params.get("open")) : null;
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");

  const orders = useApi(() => api.orders(300), [], { interval: 10000 });
  const stats = useApi(() => api.dashboard(), [], { interval: 10000 });

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (orders.data ?? []).filter((o) => {
      if (status !== "all" && o.status !== status) return false;
      if (!q) return true;
      return (
        String(o.id).includes(q.replace("#", "")) ||
        o.customer_name.toLowerCase().includes(q) ||
        o.items.some((i) => i.product_name.toLowerCase().includes(q))
      );
    });
  }, [orders.data, query, status]);

  const open = (id: number) => router.replace(`/orders?open=${id}`, { scroll: false });
  const close = () => router.replace("/orders", { scroll: false });
  const s = stats.data;
  const isNew = (o: Order) => Date.now() - new Date(o.created_at).getTime() < 10 * 60 * 1000 && o.source === "ai_agent";

  return (
    <div className="space-y-6">
      <PageHeader
        title="Orders"
        subtitle="Every order processed by KirAI."
        actions={
          <Button variant="outline" onClick={() => { orders.refetch(); stats.refetch(); }} className="gap-2">
            <RefreshCw className={`size-4 ${orders.refreshing ? "animate-spin" : ""}`} /> Refresh
          </Button>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total Orders" icon={ShoppingBag} tone="indigo" loading={!s} value={s?.total_orders ?? 0} hint={s ? `${s.ai_handled_orders} handled by KirAI` : ""} />
        <StatCard label="Today's Orders" icon={Sparkles} tone="violet" loading={!s} value={s?.orders_today ?? 0} trend={s?.orders_trend_pct} hint="vs yesterday" />
        <StatCard label="Revenue" icon={BadgeIndianRupee} tone="emerald" loading={!s} value={inr(s?.total_revenue)} hint={s ? `${inr(s.revenue_today)} today` : ""} />
        <StatCard label="Pending" icon={Clock} tone="amber" loading={!s} value={s?.pending_orders ?? 0} hint="awaiting delivery" />
      </div>

      <Card>
        <div className="flex flex-col gap-3 border-b p-4 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by order #, customer or product"
              className="h-10 w-full rounded-lg border bg-background pl-9 pr-3 text-sm outline-none transition focus:border-primary/50 focus:ring-4 focus:ring-primary/10"
              aria-label="Search orders"
            />
          </div>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="h-10 rounded-lg border bg-background px-3 text-sm outline-none focus:border-primary/50"
            aria-label="Filter by status"
          >
            <option value="all">All statuses</option>
            <option value="confirmed">Confirmed</option>
            <option value="out_for_delivery">Out for delivery</option>
            <option value="delivered">Delivered</option>
          </select>
        </div>

        {orders.loading ? (
          <RowsSkeleton rows={7} label="Loading orders..." />
        ) : orders.error && !orders.data ? (
          <ErrorState message={orders.error} onRetry={orders.reload} className="m-4 border-0" />
        ) : filtered.length === 0 ? (
          <EmptyState icon={ShoppingBag} title={orders.data?.length ? "No orders match your filters" : "No orders yet"} description={orders.data?.length ? "Try a different search or status." : "Orders created by KirAI will show up here."} />
        ) : (
          <>
            {/* desktop table */}
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="px-5 py-3 font-medium">Order</th>
                    <th className="px-3 py-3 font-medium">Customer</th>
                    <th className="px-3 py-3 font-medium">Items</th>
                    <th className="px-3 py-3 text-right font-medium">Total</th>
                    <th className="px-3 py-3 font-medium">Status</th>
                    <th className="px-5 py-3 font-medium">Date</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {filtered.map((o) => (
                    <tr key={o.id} onClick={() => open(o.id)} className="cursor-pointer transition hover:bg-muted/50">
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold tabular-nums">#{o.id}</span>
                          <SourceBadge source={o.source} />
                          {isNew(o) && <span className="rounded-full bg-emerald-500 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-white">New</span>}
                        </div>
                      </td>
                      <td className="px-3 py-3.5">{o.customer_name}</td>
                      <td className="max-w-[280px] px-3 py-3.5">
                        <p className="truncate text-muted-foreground">{o.items.map((i) => `${i.quantity} × ${i.product_name}`).join(", ")}</p>
                      </td>
                      <td className="px-3 py-3.5 text-right font-medium tabular-nums">{inr(o.total)}</td>
                      <td className="px-3 py-3.5"><OrderStatusBadge status={o.status} /></td>
                      <td className="whitespace-nowrap px-5 py-3.5 text-muted-foreground" title={dateTime(o.created_at)}>{timeAgo(o.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* mobile cards */}
            <ul className="divide-y md:hidden">
              {filtered.map((o) => (
                <li key={o.id}>
                  <button onClick={() => open(o.id)} className="w-full space-y-2 px-4 py-4 text-left transition hover:bg-muted/50">
                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-2 font-semibold">#{o.id} <SourceBadge source={o.source} /></span>
                      <OrderStatusBadge status={o.status} />
                    </div>
                    <p className="text-sm">{o.customer_name}</p>
                    <p className="line-clamp-2 text-xs text-muted-foreground">{o.items.map((i) => `${i.quantity} × ${i.product_name}`).join(", ")}</p>
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-medium tabular-nums">{inr(o.total)}</span>
                      <span className="text-xs text-muted-foreground">{timeAgo(o.created_at)}</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      <OrderDrawer orderId={openId && !Number.isNaN(openId) ? openId : null} onClose={close} onChanged={() => { orders.refetch(); stats.refetch(); }} />
    </div>
  );
}
