"use client";

import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Boxes, CircleAlert, PackageCheck, PackageX, RefreshCw, Search } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/hooks/use-api";
import { inr } from "@/lib/format";
import { Card, EmptyState, ErrorState, PageHeader, RowsSkeleton, StatCard, StockBadge, StockBar } from "@/components/shared";
import { ProductDrawer } from "@/components/inventory/product-drawer";
import { Button } from "@/components/ui/button";
import type { Product } from "@/types";

export default function InventoryPage() {
  return (
    <Suspense fallback={<RowsSkeleton rows={8} label="Loading products..." />}>
      <InventoryView />
    </Suspense>
  );
}

function InventoryView() {
  const params = useSearchParams();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [category, setCategory] = useState("all");
  const [status, setStatus] = useState("all");
  const [selected, setSelected] = useState<Product | null>(null);

  const inv = useApi(() => api.inventory(), [], { interval: 8000 });
  const summary = inv.data?.summary;

  const products = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (inv.data?.products ?? []).filter((p) => {
      if (category !== "all" && p.category !== category) return false;
      if (status !== "all" && p.stock_status !== status) return false;
      if (!q) return true;
      return [p.name, p.brand, p.category, p.aliases].some((f) => f.toLowerCase().includes(q));
    });
  }, [inv.data, query, category, status]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Inventory"
        subtitle="Monitor your store stock in real time."
        actions={
          <Button variant="outline" onClick={() => inv.refetch()} className="gap-2">
            <RefreshCw className={`size-4 ${inv.refreshing ? "animate-spin" : ""}`} /> Refresh
          </Button>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Products" icon={Boxes} tone="indigo" loading={!summary} value={summary?.total_products ?? 0} hint={summary ? `${summary.total_units.toLocaleString("en-IN")} units on shelf` : ""} />
        <StatCard label="In Stock" icon={PackageCheck} tone="emerald" loading={!summary} value={summary?.in_stock ?? 0} hint="healthy levels" />
        <StatCard label="Low Stock" icon={CircleAlert} tone="amber" loading={!summary} value={summary?.low_stock ?? 0} hint="reorder soon" />
        <StatCard label="Out of Stock" icon={PackageX} tone="red" loading={!summary} value={summary?.out_of_stock ?? 0} hint={summary ? `Stock value ${inr(summary.stock_value)}` : ""} />
      </div>

      <Card>
        <div className="flex flex-col gap-3 border-b p-4 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search products, brands or Hinglish names (atta, doodh...)"
              className="h-10 w-full rounded-lg border bg-background pl-9 pr-3 text-sm outline-none transition focus:border-primary/50 focus:ring-4 focus:ring-primary/10"
              aria-label="Search products"
            />
          </div>
          <div className="flex gap-2">
            <select value={category} onChange={(e) => setCategory(e.target.value)} className="h-10 flex-1 rounded-lg border bg-background px-3 text-sm outline-none focus:border-primary/50 lg:flex-none" aria-label="Filter by category">
              <option value="all">All categories</option>
              {(inv.data?.categories ?? []).map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <select value={status} onChange={(e) => setStatus(e.target.value)} className="h-10 flex-1 rounded-lg border bg-background px-3 text-sm outline-none focus:border-primary/50 lg:flex-none" aria-label="Filter by stock status">
              <option value="all">All stock levels</option>
              <option value="in_stock">In Stock</option>
              <option value="low_stock">Low Stock</option>
              <option value="out_of_stock">Out of Stock</option>
            </select>
          </div>
        </div>

        {inv.loading ? (
          <RowsSkeleton rows={8} label="Loading products..." />
        ) : inv.error && !inv.data ? (
          <ErrorState message={inv.error} onRetry={inv.reload} className="m-4 border-0" />
        ) : products.length === 0 ? (
          <EmptyState icon={Search} title="No products found" description="Try a different search or clear the filters." />
        ) : (
          <>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="px-5 py-3 font-medium">Product</th>
                    <th className="px-3 py-3 font-medium">Category</th>
                    <th className="px-3 py-3 text-right font-medium">Price</th>
                    <th className="px-3 py-3 font-medium">Stock</th>
                    <th className="px-3 py-3 font-medium">Status</th>
                    <th className="px-5 py-3 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {products.map((p) => (
                    <tr key={p.id} onClick={() => setSelected(p)} className="cursor-pointer transition hover:bg-muted/50">
                      <td className="px-5 py-3.5">
                        <p className="font-medium">{p.name}</p>
                        <p className="text-xs text-muted-foreground">{p.brand}</p>
                      </td>
                      <td className="px-3 py-3.5 text-muted-foreground">{p.category}</td>
                      <td className="px-3 py-3.5 text-right font-medium tabular-nums">{inr(p.price)}</td>
                      <td className="px-3 py-3.5"><StockBar quantity={p.stock_quantity} threshold={p.low_stock_threshold} status={p.stock_status} /></td>
                      <td className="px-3 py-3.5"><StockBadge status={p.stock_status} /></td>
                      <td className="px-5 py-3.5 text-right">
                        <button onClick={(e) => { e.stopPropagation(); setSelected(p); }} className="rounded-lg border px-3 py-1.5 text-xs font-medium transition hover:bg-muted">
                          Details
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <ul className="divide-y md:hidden">
              {products.map((p) => (
                <li key={p.id}>
                  <button onClick={() => setSelected(p)} className="w-full space-y-2.5 px-4 py-4 text-left transition hover:bg-muted/50">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-medium">{p.name}</p>
                        <p className="text-xs text-muted-foreground">{p.category} · {inr(p.price)}</p>
                      </div>
                      <StockBadge status={p.stock_status} />
                    </div>
                    <StockBar quantity={p.stock_quantity} threshold={p.low_stock_threshold} status={p.stock_status} />
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      <ProductDrawer product={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
