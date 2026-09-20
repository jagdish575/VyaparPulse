"use client";

import Link from "next/link";
import {
  BadgeIndianRupee,
  Boxes,
  CircleHelp,
  CircleX,
  MessageCircleCheck,
  PackageMinus,
  Search,
  ShoppingBag,
  Sparkles,
  Truck,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { timeAgo, timeOfDay } from "@/lib/format";
import type { Activity } from "@/types";

export const ACTION_META: Record<string, { icon: LucideIcon; label: string }> = {
  request_parsed: { icon: Sparkles, label: "Request parsed" },
  products_matched: { icon: Search, label: "Products matched" },
  inventory_verified: { icon: Boxes, label: "Inventory verified" },
  prices_verified: { icon: BadgeIndianRupee, label: "Prices verified" },
  order_created: { icon: ShoppingBag, label: "Order created" },
  inventory_updated: { icon: PackageMinus, label: "Inventory updated" },
  confirmation_sent: { icon: MessageCircleCheck, label: "Confirmation ready" },
  request_rejected: { icon: CircleX, label: "Request rejected" },
  clarification_requested: { icon: CircleHelp, label: "Clarification requested" },
  stock_checked: { icon: Search, label: "Stock checked" },
  low_stock_report: { icon: TriangleAlert, label: "Low-stock report" },
  order_status_changed: { icon: Truck, label: "Order status changed" },
};

export function activityTone(status: string) {
  if (status === "failed") return "bg-red-50 text-red-600 ring-red-500/20";
  if (status === "needs_input") return "bg-amber-50 text-amber-600 ring-amber-500/20";
  if (status === "info") return "bg-sky-50 text-sky-600 ring-sky-500/20";
  return "bg-indigo-50 text-indigo-600 ring-indigo-500/20";
}

export function ActivityIcon({ action, status, className }: { action: string; status: string; className?: string }) {
  const Icon = (ACTION_META[action] ?? ACTION_META.request_parsed).icon;
  return (
    <div className={cn("flex size-8 shrink-0 items-center justify-center rounded-full ring-1 ring-inset", activityTone(status), className)}>
      <Icon className="size-4" />
    </div>
  );
}

/** Compact feed used on the dashboard. */
export function ActivityMiniList({ items }: { items: Activity[] }) {
  return (
    <ul className="divide-y">
      {items.map((a) => (
        <li key={a.id} className="flex items-start gap-3 px-5 py-3">
          <ActivityIcon action={a.action} status={a.status} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">
              {a.order_id ? (
                <Link href={`/orders?open=${a.order_id}`} className="hover:underline">
                  {a.message}
                </Link>
              ) : (
                a.message
              )}
            </p>
            <p className="text-xs text-muted-foreground">
              {timeOfDay(a.created_at, true)} · {timeAgo(a.created_at)}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}
