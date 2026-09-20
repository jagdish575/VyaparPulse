"use client";

import { useState } from "react";
import { Boxes, CheckCheck, MapPin, Phone, Quote, Truck, User } from "lucide-react";
import { toast } from "sonner";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/hooks/use-api";
import { dateTime, inr, timeOfDay } from "@/lib/format";
import { ACTION_META, ActivityIcon } from "@/components/activity-feed";
import { ErrorState, OrderStatusBadge, SourceBadge } from "@/components/shared";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      {children}
    </section>
  );
}

export function OrderDrawer({ orderId, onClose, onChanged }: { orderId: number | null; onClose: () => void; onChanged?: () => void }) {
  const { data: order, loading, error, reload } = useApi(() => api.order(orderId as number), [orderId], { enabled: orderId != null });
  const [busy, setBusy] = useState(false);

  const setStatus = async (status: "out_for_delivery" | "delivered") => {
    if (!order) return;
    setBusy(true);
    try {
      await api.setOrderStatus(order.id, status);
      toast.success(status === "delivered" ? "Order marked as delivered." : "Order is out for delivery.");
      await reload();
      onChanged?.();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "We couldn't update the order.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={orderId != null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="gap-0 overflow-y-auto p-0 data-[side=right]:w-full data-[side=right]:sm:max-w-lg">
        <SheetHeader className="border-b px-6 py-5">
          <SheetTitle className="flex items-center gap-3 text-xl">
            Order #{orderId}
            {order && <OrderStatusBadge status={order.status} />}
          </SheetTitle>
          <SheetDescription>
            {order ? (
              <span className="flex items-center gap-2">
                {dateTime(order.created_at)} <SourceBadge source={order.source} />
              </span>
            ) : (
              "Order details"
            )}
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-7 px-6 py-6">
          {loading && !order ? (
            <div className="space-y-4" role="status" aria-label="Loading order">
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-32 w-full" />
              <Skeleton className="h-40 w-full" />
            </div>
          ) : error && !order ? (
            <ErrorState message={error} onRetry={reload} />
          ) : order ? (
            <>
              <Section title="Customer">
                <div className="space-y-2 rounded-xl border bg-muted/30 p-4 text-sm">
                  <p className="flex items-center gap-2 font-medium"><User className="size-4 text-muted-foreground" />{order.customer.name}</p>
                  <p className="flex items-center gap-2 text-muted-foreground"><Phone className="size-4" />{order.customer.phone}</p>
                  <p className="flex items-center gap-2 text-muted-foreground"><MapPin className="size-4" />{order.delivery_address}</p>
                </div>
                {order.original_request && (
                  <div className="flex gap-2.5 rounded-xl border border-violet-200 bg-violet-50/50 p-4 text-sm">
                    <Quote className="mt-0.5 size-4 shrink-0 text-violet-500" />
                    <p className="italic text-foreground/80">{order.original_request}</p>
                  </div>
                )}
              </Section>

              <Section title="Items">
                <ul className="divide-y rounded-xl border">
                  {order.items.map((i) => (
                    <li key={i.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                      <div>
                        <p className="font-medium">{i.product_name}</p>
                        <p className="text-xs text-muted-foreground">{i.quantity} × {inr(i.unit_price)}</p>
                      </div>
                      <p className="font-medium tabular-nums">{inr(i.line_total)}</p>
                    </li>
                  ))}
                </ul>
                <dl className="space-y-1.5 text-sm">
                  <div className="flex justify-between text-muted-foreground"><dt>Subtotal</dt><dd className="tabular-nums">{inr(order.subtotal)}</dd></div>
                  <div className="flex justify-between text-muted-foreground"><dt>Delivery</dt><dd className="tabular-nums">{order.delivery_charge ? inr(order.delivery_charge) : "Free"}</dd></div>
                  <div className="flex justify-between border-t pt-2 text-base font-semibold"><dt>Total</dt><dd className="tabular-nums">{inr(order.total)}</dd></div>
                </dl>
              </Section>

              <Section title="AI processing">
                {order.activity.length === 0 ? (
                  <p className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
                    {order.source === "ai_agent" ? "No processing steps were recorded." : "This order came from sample data, so KirAI has no processing steps for it."}
                  </p>
                ) : (
                  <ol className="space-y-0.5">
                    {order.activity.map((a, idx) => (
                      <li key={a.id} className="relative flex gap-3 pb-4 last:pb-0">
                        {idx < order.activity.length - 1 && <span className="absolute left-4 top-8 h-[calc(100%-20px)] w-px bg-border" />}
                        <ActivityIcon action={a.action} status={a.status} />
                        <div className="min-w-0 flex-1 pt-0.5">
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-sm font-medium">{(ACTION_META[a.action]?.label) ?? a.action}</p>
                            <span className="font-mono text-[11px] tabular-nums text-muted-foreground">{timeOfDay(a.created_at, true)}</span>
                          </div>
                          <p className="text-[13px] text-muted-foreground">{a.message}</p>
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
              </Section>

              <Section title="Inventory changes">
                {order.inventory_changes.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No inventory changes recorded.</p>
                ) : (
                  <ul className="divide-y rounded-xl border">
                    {order.inventory_changes.map((c) => (
                      <li key={c.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                        <span className="flex items-center gap-2"><Boxes className="size-4 text-muted-foreground" />{c.product_name}</span>
                        <span className="tabular-nums text-muted-foreground">
                          {c.stock_before} → <b className="text-foreground">{c.stock_after}</b>{" "}
                          <span className="ml-1 rounded bg-red-50 px-1.5 py-0.5 text-xs font-medium text-red-600">{c.quantity_change}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Section>

              {(order.status === "confirmed" || order.status === "out_for_delivery") && (
                <div className="flex flex-wrap gap-2 border-t pt-5">
                  {order.status === "confirmed" && (
                    <Button variant="outline" disabled={busy} onClick={() => setStatus("out_for_delivery")} className="gap-2">
                      <Truck className="size-4" /> Out for delivery
                    </Button>
                  )}
                  <Button disabled={busy} onClick={() => setStatus("delivered")} className="gap-2">
                    <CheckCheck className="size-4" /> Mark delivered
                  </Button>
                </div>
              )}
            </>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
