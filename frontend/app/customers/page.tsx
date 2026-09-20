"use client";

import { useState } from "react";
import { MapPin, Phone, RefreshCw, Users } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/hooks/use-api";
import { dateTime, inr, timeAgo } from "@/lib/format";
import { ActivityMiniList } from "@/components/activity-feed";
import { Card, EmptyState, ErrorState, OrderStatusBadge, PageHeader, RowsSkeleton } from "@/components/shared";
import type { CustomerSummary } from "@/types";

function initials(name: string) {
  return name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();
}

function Avatar({ name, size = "size-9" }: { name: string; size?: string }) {
  return (
    <div className={`${size} flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-100 to-violet-100 text-xs font-semibold text-indigo-700`}>
      {initials(name)}
    </div>
  );
}

export default function CustomersPage() {
  const customers = useApi(() => api.customers(), [], { interval: 10000 });
  const [selected, setSelected] = useState<CustomerSummary | null>(null);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Customers"
        subtitle="The people KirAI serves, with their real order history."
        actions={
          <Button variant="outline" onClick={() => customers.refetch()} className="gap-2">
            <RefreshCw className={`size-4 ${customers.refreshing ? "animate-spin" : ""}`} /> Refresh
          </Button>
        }
      />

      <Card>
        {customers.loading ? (
          <RowsSkeleton rows={5} label="Loading customers..." />
        ) : customers.error && !customers.data ? (
          <ErrorState message={customers.error} onRetry={customers.reload} className="m-4 border-0" />
        ) : !customers.data?.length ? (
          <EmptyState icon={Users} title="No customers yet" />
        ) : (
          <>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="px-5 py-3 font-medium">Customer</th>
                    <th className="px-3 py-3 font-medium">Phone</th>
                    <th className="px-3 py-3 text-right font-medium">Orders</th>
                    <th className="px-3 py-3 text-right font-medium">Total Spent</th>
                    <th className="px-5 py-3 font-medium">Last Order</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {customers.data.map((c) => (
                    <tr key={c.id} onClick={() => setSelected(c)} className="cursor-pointer transition hover:bg-muted/50">
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-3">
                          <Avatar name={c.name} />
                          <div>
                            <p className="font-medium">{c.name}</p>
                            <p className="text-xs text-muted-foreground">{c.address}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-3.5 tabular-nums text-muted-foreground">{c.phone}</td>
                      <td className="px-3 py-3.5 text-right tabular-nums">{c.orders_count}</td>
                      <td className="px-3 py-3.5 text-right font-medium tabular-nums">{inr(c.total_spent)}</td>
                      <td className="px-5 py-3.5 text-muted-foreground">{c.last_order_at ? timeAgo(c.last_order_at) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="divide-y md:hidden">
              {customers.data.map((c) => (
                <li key={c.id}>
                  <button onClick={() => setSelected(c)} className="flex w-full items-center gap-3 px-4 py-4 text-left transition hover:bg-muted/50">
                    <Avatar name={c.name} size="size-10" />
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{c.name}</p>
                      <p className="text-xs text-muted-foreground">{c.orders_count} orders · last {c.last_order_at ? timeAgo(c.last_order_at) : "—"}</p>
                    </div>
                    <p className="font-medium tabular-nums">{inr(c.total_spent)}</p>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      <CustomerDrawer customer={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

function CustomerDrawer({ customer, onClose }: { customer: CustomerSummary | null; onClose: () => void }) {
  const id = customer?.id ?? null;
  const { data, loading, error, reload } = useApi(() => api.customer(id as number), [id], { enabled: id != null });
  const c = data && data.id === id ? data : customer;

  return (
    <Sheet open={customer != null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="gap-0 overflow-y-auto p-0 data-[side=right]:w-full data-[side=right]:sm:max-w-lg">
        <SheetHeader className="border-b px-6 py-5">
          <div className="flex items-center gap-3">
            {c && <Avatar name={c.name} size="size-11" />}
            <div>
              <SheetTitle className="text-xl">{c?.name ?? "Customer"}</SheetTitle>
              <SheetDescription>Customer since {c ? dateTime(c.created_at) : ""}</SheetDescription>
            </div>
          </div>
        </SheetHeader>
        {c && (
          <div className="space-y-7 px-6 py-6">
            <div className="space-y-2 rounded-xl border bg-muted/30 p-4 text-sm">
              <p className="flex items-center gap-2 text-muted-foreground"><Phone className="size-4" />{c.phone}</p>
              <p className="flex items-center gap-2 text-muted-foreground"><MapPin className="size-4" />{c.address}</p>
            </div>

            <div className="grid grid-cols-3 gap-3">
              {[
                ["Orders", String(c.orders_count)],
                ["Total spent", inr(c.total_spent)],
                ["Avg. order", data && data.id === id ? inr(data.average_order_value) : "…"],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl border p-3.5">
                  <p className="text-xs text-muted-foreground">{label}</p>
                  <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
                </div>
              ))}
            </div>

            {loading && !data ? (
              <div className="space-y-2" role="status" aria-label="Loading customer"><Skeleton className="h-14 w-full" /><Skeleton className="h-14 w-full" /><Skeleton className="h-14 w-full" /></div>
            ) : error && !data ? (
              <ErrorState message={error} onRetry={reload} className="py-8" />
            ) : data ? (
              <>
                <section className="space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Order history</h3>
                  {data.orders.length === 0 ? (
                    <p className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground">No orders yet.</p>
                  ) : (
                    <ul className="divide-y rounded-xl border">
                      {data.orders.map((o) => (
                        <li key={o.id}>
                          <Link href={`/orders?open=${o.id}`} className="flex items-center justify-between gap-3 px-4 py-3 transition hover:bg-muted/50">
                            <div className="min-w-0">
                              <p className="text-sm font-medium">#{o.id} <span className="ml-1 text-xs font-normal text-muted-foreground">{timeAgo(o.created_at)}</span></p>
                              <p className="truncate text-xs text-muted-foreground">{o.items.map((i) => `${i.quantity} × ${i.product_name}`).join(", ")}</p>
                            </div>
                            <div className="flex shrink-0 flex-col items-end gap-1">
                              <span className="text-sm font-medium tabular-nums">{inr(o.total)}</span>
                              <OrderStatusBadge status={o.status} />
                            </div>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
                <section className="space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Recent activity</h3>
                  {data.recent_activity.length ? (
                    <div className="overflow-hidden rounded-xl border"><ActivityMiniList items={data.recent_activity} /></div>
                  ) : (
                    <p className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground">No activity yet.</p>
                  )}
                </section>
              </>
            ) : null}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
