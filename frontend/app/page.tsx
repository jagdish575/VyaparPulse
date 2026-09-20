"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowRight, BadgeIndianRupee, Boxes, PackageCheck, ShoppingBag, Sparkles, TriangleAlert } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/hooks/use-api";
import { greeting, inr, timeAgo } from "@/lib/format";
import { ActivityMiniList } from "@/components/activity-feed";
import {
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  OrderStatusBadge,
  PageHeader,
  RowsSkeleton,
  StatCard,
  StockBar,
  StockBadge,
} from "@/components/shared";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SUGGESTIONS = ["Order 2 Maggi", "Check atta stock", "Show low stock"];

export default function DashboardPage() {
  const router = useRouter();
  const [command, setCommand] = useState("");
  const [hello, setHello] = useState("Good morning"); // set after mount to avoid a server/client time mismatch
  useEffect(() => setHello(greeting()), []);
  const stats = useApi(() => api.dashboard(), [], { interval: 15000 });
  const orders = useApi(() => api.orders(6), [], { interval: 15000 });
  const inventory = useApi(() => api.inventory(), [], { interval: 15000 });
  const activity = useApi(() => api.activity(7), [], { interval: 15000 });

  const s = stats.data;
  const lowStock = (inventory.data?.products ?? [])
    .filter((p) => p.stock_status !== "in_stock")
    .sort((a, b) => a.stock_quantity - b.stock_quantity)
    .slice(0, 6);
  const maxRevenue = Math.max(1, ...(s?.daily.map((d) => d.revenue) ?? [1]));

  const runCommand = (text: string) => {
    const q = text.trim();
    if (q) router.push(`/operator?q=${encodeURIComponent(q)}`);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={`${hello}, Rahul 👋`}
        subtitle="Here's what's happening in your store today."
        actions={
          <Link href="/operator" className={cn(buttonVariants(), "gap-2")}>
            <Sparkles className="size-4" /> Open AI Operator
          </Link>
        }
      />

      {stats.error && !s ? (
        <ErrorState message={stats.error} onRetry={stats.reload} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Today's Orders"
            icon={ShoppingBag}
            tone="indigo"
            loading={!s}
            value={s?.orders_today ?? 0}
            trend={s?.orders_trend_pct}
            hint={s ? `${s.yesterday.orders} yesterday` : ""}
          />
          <StatCard
            label="Revenue"
            icon={BadgeIndianRupee}
            tone="emerald"
            loading={!s}
            value={inr(s?.revenue_today)}
            trend={s?.revenue_trend_pct}
            hint={s ? `${inr(s.yesterday.revenue)} yesterday` : ""}
          />
          <StatCard
            label="Items Sold"
            icon={PackageCheck}
            tone="violet"
            loading={!s}
            value={s?.items_sold_today ?? 0}
            trend={s?.items_trend_pct}
            hint={s ? `${s.yesterday.items} yesterday` : ""}
          />
          <StatCard
            label="Low Stock"
            icon={TriangleAlert}
            tone={s && s.low_stock_count > 0 ? "amber" : "emerald"}
            loading={!s}
            value={s?.low_stock_count ?? 0}
            hint={s ? `${s.out_of_stock_count} out of stock` : ""}
          />
        </div>
      )}

      {/* Quick AI command */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="overflow-hidden rounded-2xl border border-primary/20 bg-gradient-to-br from-indigo-50/70 via-card to-violet-50/50 shadow-sm"
      >
        <div className="h-1 bg-gradient-to-r from-indigo-600 via-violet-500 to-blue-500" />
        <div className="flex flex-col gap-3 p-4 sm:p-5">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <span className="flex size-6 items-center justify-center rounded-md bg-gradient-to-br from-indigo-600 to-violet-500 text-white">
              <Sparkles className="size-3.5" />
            </span>
            Quick AI Command
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              runCommand(command);
            }}
            className="flex items-center gap-2 rounded-xl border bg-background p-1.5 pl-3.5 transition focus-within:border-primary/50 focus-within:ring-4 focus-within:ring-primary/10"
          >
            <input
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder="Ask KirAI to manage your store..."
              className="min-w-0 flex-1 bg-transparent py-2 text-[15px] outline-none placeholder:text-muted-foreground/70"
              aria-label="Quick AI command"
            />
            <button
              type="submit"
              disabled={!command.trim()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-indigo-600 to-violet-500 px-3.5 py-2 text-sm font-medium text-white transition hover:brightness-110 disabled:opacity-40"
            >
              Run <ArrowRight className="size-4" />
            </button>
          </form>
          <div className="flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((q) => (
              <button
                key={q}
                onClick={() => runCommand(q)}
                className="rounded-full border bg-background px-3 py-1 text-xs font-medium text-muted-foreground transition hover:border-primary/40 hover:text-foreground"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      </motion.div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Recent orders */}
        <Card className="lg:col-span-2">
          <CardHeader
            title="Recent Orders"
            description="Latest orders processed by KirAI"
            action={
              <Link href="/orders" className="text-sm font-medium text-primary hover:underline">
                View all
              </Link>
            }
          />
          {orders.loading ? (
            <RowsSkeleton rows={5} label="Loading orders..." />
          ) : orders.error && !orders.data ? (
            <ErrorState message={orders.error} onRetry={orders.reload} className="m-4 border-0" />
          ) : orders.data && orders.data.length > 0 ? (
            <ul className="divide-y">
              {orders.data.map((o) => (
                <li key={o.id}>
                  <Link href={`/orders?open=${o.id}`} className="flex items-center gap-4 px-5 py-3.5 transition hover:bg-muted/50">
                    <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
                      <ShoppingBag className="size-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium">
                        #{o.id} · {o.customer_name}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {o.items.map((i) => `${i.quantity} × ${i.product_name}`).join(", ")}
                      </p>
                    </div>
                    <div className="hidden text-right sm:block">
                      <p className="text-sm font-medium tabular-nums">{inr(o.total)}</p>
                      <p className="text-xs text-muted-foreground">{timeAgo(o.created_at)}</p>
                    </div>
                    <OrderStatusBadge status={o.status} />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No orders yet" description="Send a customer request in the AI Operator to create the first order." />
          )}
        </Card>

        {/* Low stock */}
        <Card>
          <CardHeader
            title="Low Stock Products"
            description="Needs restocking soon"
            action={
              <Link href="/inventory" className="text-sm font-medium text-primary hover:underline">
                Inventory
              </Link>
            }
          />
          {inventory.loading ? (
            <RowsSkeleton rows={4} label="Checking inventory..." />
          ) : inventory.error && !inventory.data ? (
            <ErrorState message={inventory.error} onRetry={inventory.reload} className="m-4 border-0" />
          ) : lowStock.length ? (
            <ul className="divide-y">
              {lowStock.map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-3 px-5 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{p.name}</p>
                    <div className="mt-1.5">
                      <StockBar quantity={p.stock_quantity} threshold={p.low_stock_threshold} status={p.stock_status} />
                    </div>
                  </div>
                  <StockBadge status={p.stock_status} />
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon={Boxes} title="Everything is well stocked" />
          )}
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Revenue chart */}
        <Card className="lg:col-span-2">
          <CardHeader title="Last 7 days" description="Revenue by day (from real orders)" />
          <div className="px-5 pb-5 pt-6">
            {!s ? (
              <RowsSkeleton rows={2} />
            ) : (
              <div className="flex h-44 items-end gap-3 sm:gap-5" role="img" aria-label="Revenue for the last 7 days">
                {s.daily.map((d, i) => {
                  const isToday = i === s.daily.length - 1;
                  const h = Math.max(d.revenue > 0 ? 6 : 2, (d.revenue / maxRevenue) * 100);
                  return (
                    <div key={i} className="group flex flex-1 flex-col items-center gap-2" title={`${d.orders} orders · ${inr(d.revenue)}`}>
                      <span className="text-[11px] font-medium tabular-nums text-muted-foreground opacity-0 transition group-hover:opacity-100">
                        {inr(d.revenue)}
                      </span>
                      <div className="flex h-full w-full items-end">
                        <motion.div
                          initial={{ height: 0 }}
                          animate={{ height: `${h}%` }}
                          transition={{ duration: 0.6, delay: i * 0.05 }}
                          className={cn(
                            "w-full rounded-t-lg",
                            isToday ? "bg-gradient-to-t from-indigo-600 to-violet-500" : "bg-indigo-100 group-hover:bg-indigo-200"
                          )}
                        />
                      </div>
                      <span className={cn("text-xs", isToday ? "font-semibold text-foreground" : "text-muted-foreground")}>
                        {isToday ? "Today" : d.date}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </Card>

        {/* AI activity */}
        <Card>
          <CardHeader
            title="AI Activity"
            description="What KirAI just did"
            action={
              <Link href="/activity" className="text-sm font-medium text-primary hover:underline">
                View all
              </Link>
            }
          />
          {activity.loading ? (
            <RowsSkeleton rows={4} />
          ) : activity.error && !activity.data ? (
            <ErrorState message={activity.error} onRetry={activity.reload} className="m-4 border-0" />
          ) : activity.data && activity.data.length ? (
            <ActivityMiniList items={activity.data} />
          ) : (
            <EmptyState title="No activity yet" description="KirAI's actions will appear here." />
          )}
        </Card>
      </div>
    </div>
  );
}

