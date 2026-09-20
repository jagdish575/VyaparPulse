"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, CheckCircle2, MapPin, PackageCheck, User } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { inr, STATUS_LABEL } from "@/lib/format";
import type { AgentOrder } from "@/types";

export function OrderConfirmationCard({ order, showInventory }: { order: AgentOrder; showInventory: boolean }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 260, damping: 24 }}
      className="overflow-hidden rounded-2xl border border-emerald-200 bg-card shadow-[0_8px_30px_-12px_rgba(16,185,129,0.35)]"
    >
      <div className="flex items-center justify-between gap-3 border-b border-emerald-100 bg-emerald-50/70 px-5 py-4">
        <div className="flex items-center gap-3">
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: "spring", stiffness: 380, damping: 14, delay: 0.1 }}
            className="flex size-9 items-center justify-center rounded-full bg-emerald-500 text-white"
          >
            <CheckCircle2 className="size-5" />
          </motion.div>
          <div>
            <p className="text-base font-semibold text-emerald-900">Order Confirmed</p>
            <p className="text-xs text-emerald-700/80">Created by KirAI and saved to the database</p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-xs text-muted-foreground">Order</p>
          <p className="text-lg font-semibold tabular-nums">#{order.id}</p>
        </div>
      </div>

      <div className="grid gap-6 p-5 md:grid-cols-2">
        <div className="space-y-4">
          <div className="flex items-start gap-3">
            <User className="mt-0.5 size-4 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Customer</p>
              <p className="text-sm font-medium">{order.customer.name}</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <MapPin className="mt-0.5 size-4 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Delivery</p>
              <p className="text-sm font-medium">{order.delivery_address}</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <PackageCheck className="mt-0.5 size-4 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Status</p>
              <span className="mt-0.5 inline-flex items-center rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-700">
                {STATUS_LABEL[order.status] ?? order.status}
              </span>
            </div>
          </div>
        </div>

        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Items</p>
          <ul className="divide-y divide-border/70">
            {order.items.map((item, i) => (
              <motion.li
                key={item.id}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.12 + i * 0.07 }}
                className="flex items-center justify-between gap-4 py-2 text-sm"
              >
                <span>
                  <span className="font-medium tabular-nums">{item.quantity} ×</span> {item.product_name}
                </span>
                <span className="font-medium tabular-nums">{inr(item.line_total)}</span>
              </motion.li>
            ))}
          </ul>
          <dl className="mt-3 space-y-1.5 border-t border-dashed pt-3 text-sm">
            <div className="flex justify-between text-muted-foreground">
              <dt>Subtotal</dt>
              <dd className="tabular-nums">{inr(order.subtotal)}</dd>
            </div>
            <div className="flex justify-between text-muted-foreground">
              <dt>Delivery</dt>
              <dd className="tabular-nums">{order.delivery_charge ? inr(order.delivery_charge) : "Free"}</dd>
            </div>
            <div className="flex justify-between pt-1 text-base font-semibold">
              <dt>Total</dt>
              <dd className="tabular-nums">{inr(order.total)}</dd>
            </div>
          </dl>
        </div>
      </div>

      <div className="flex flex-col gap-3 border-t bg-muted/30 px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between">
        {showInventory ? (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-wrap items-center gap-1.5 text-xs"
          >
            <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 font-medium text-primary">
              <PackageCheck className="size-3.5" /> Inventory updated
            </span>
            {order.inventory_changes.map((c) => (
              <span key={c.id} className="rounded-full border bg-card px-2 py-1 text-muted-foreground tabular-nums">
                {c.product_name.replace(/ \d.*$/, "")}: {c.stock_before} → <b className="text-foreground">{c.stock_after}</b>
              </span>
            ))}
          </motion.div>
        ) : (
          <span />
        )}
        <Link
          href={`/orders?open=${order.id}`}
          className={cn(buttonVariants({ size: "sm" }), "shrink-0 gap-1.5")}
        >
          View Order <ArrowRight className="size-4" />
        </Link>
      </div>
    </motion.div>
  );
}
