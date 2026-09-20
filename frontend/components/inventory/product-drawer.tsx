"use client";

import Link from "next/link";
import { ArrowDownRight, History } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useApi } from "@/hooks/use-api";
import { dateTime, inr } from "@/lib/format";
import { ErrorState, StockBadge, StockBar } from "@/components/shared";
import type { Product } from "@/types";

export function ProductDrawer({ product, onClose }: { product: Product | null; onClose: () => void }) {
  const id = product?.id ?? null;
  const { data, loading, error, reload } = useApi(() => api.product(id as number), [id], { enabled: id != null });
  const p = data && data.id === id ? data : product;

  return (
    <Sheet open={product != null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="gap-0 overflow-y-auto p-0 data-[side=right]:w-full data-[side=right]:sm:max-w-md">
        <SheetHeader className="border-b px-6 py-5">
          <SheetTitle className="text-xl">{p?.name ?? "Product"}</SheetTitle>
          <SheetDescription>{p ? `${p.brand} · ${p.category}` : "Product details"}</SheetDescription>
        </SheetHeader>

        {p && (
          <div className="space-y-7 px-6 py-6">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl border bg-muted/30 p-4">
                <p className="text-xs text-muted-foreground">Price</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums">{inr(p.price)}</p>
                <p className="text-xs text-muted-foreground">per {p.unit}</p>
              </div>
              <div className="rounded-xl border bg-muted/30 p-4">
                <p className="text-xs text-muted-foreground">In stock</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums">{p.stock_quantity}</p>
                <div className="mt-1"><StockBadge status={p.stock_status} /></div>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Stock level</span>
                <span className="text-xs text-muted-foreground">Low-stock alert at {p.low_stock_threshold}</span>
              </div>
              <StockBar quantity={p.stock_quantity} threshold={p.low_stock_threshold} status={p.stock_status} />
            </div>

            {p.description && (
              <div className="space-y-1.5">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">About</h3>
                <p className="text-sm text-foreground/80">{p.description}</p>
              </div>
            )}

            {p.aliases && (
              <div className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Also known as</h3>
                <div className="flex flex-wrap gap-1.5">
                  {p.aliases.split(",").map((a) => (
                    <span key={a} className="rounded-full border bg-background px-2.5 py-0.5 text-xs text-muted-foreground">{a.trim()}</span>
                  ))}
                </div>
              </div>
            )}

            <div className="space-y-3">
              <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <History className="size-3.5" /> Stock movements
              </h3>
              {loading && !data ? (
                <div className="space-y-2" role="status" aria-label="Loading stock history"><Skeleton className="h-12 w-full" /><Skeleton className="h-12 w-full" /></div>
              ) : error && !data ? (
                <ErrorState message={error} onRetry={reload} className="py-8" />
              ) : data && data.logs.length > 0 ? (
                <ul className="divide-y rounded-xl border">
                  {data.logs.map((l) => (
                    <li key={l.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                      <div>
                        <p className="flex items-center gap-1.5 font-medium">
                          <ArrowDownRight className="size-4 text-red-500" />
                          {l.order_id ? (
                            <Link href={`/orders?open=${l.order_id}`} className="hover:underline">Order #{l.order_id}</Link>
                          ) : (
                            l.change_type.replace("_", " ")
                          )}
                        </p>
                        <p className="text-xs text-muted-foreground">{dateTime(l.created_at)}</p>
                      </div>
                      <p className="tabular-nums text-muted-foreground">
                        {l.stock_before} → <b className="text-foreground">{l.stock_after}</b>{" "}
                        <span className="ml-1 rounded bg-red-50 px-1.5 py-0.5 text-xs font-medium text-red-600">{l.quantity_change}</span>
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground">No stock movements yet.</p>
              )}
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
