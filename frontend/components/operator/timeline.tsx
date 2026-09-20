"use client";

import { motion } from "framer-motion";
import {
  BadgeIndianRupee,
  Boxes,
  Check,
  ClipboardCheck,
  Loader2,
  MessageCircleCheck,
  Minus,
  PackageMinus,
  Search,
  Sparkles,
  X,
  CircleHelp,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { timeOfDay } from "@/lib/format";
import type { StepStatus } from "@/types";

export type TimelineStatus = StepStatus | "pending" | "active";

export interface TimelineItem {
  key: string;
  title: string;
  description: string;
  status: TimelineStatus;
  timestamp?: string | null;
  duration_ms?: number | null;
  tools?: string[];
}

export const STEP_META: Record<string, { icon: LucideIcon; idle: string }> = {
  parse_request: { icon: Sparkles, idle: "Reads the customer's message (English / Hinglish)" },
  find_products: { icon: Search, idle: "Matches names to real catalogue products" },
  check_inventory: { icon: Boxes, idle: "Reads live stock from the database" },
  calculate_total: { icon: BadgeIndianRupee, idle: "Prices come from the database, never the AI" },
  create_order: { icon: ClipboardCheck, idle: "Order + items saved in one transaction" },
  update_inventory: { icon: PackageMinus, idle: "Stock deducted and logged atomically" },
  send_confirmation: { icon: MessageCircleCheck, idle: "Prepares the confirmation for the customer" },
};

export const PIPELINE: { key: string; title: string }[] = [
  { key: "parse_request", title: "Understanding request" },
  { key: "find_products", title: "Finding products" },
  { key: "check_inventory", title: "Checking inventory" },
  { key: "calculate_total", title: "Verifying prices" },
  { key: "create_order", title: "Creating order" },
  { key: "update_inventory", title: "Updating inventory" },
  { key: "send_confirmation", title: "Confirming with customer" },
];

const RING: Record<TimelineStatus, string> = {
  pending: "border-border bg-card text-muted-foreground/60",
  active: "border-primary/40 bg-primary/10 text-primary",
  completed: "border-emerald-500 bg-emerald-500 text-white",
  failed: "border-red-500 bg-red-500 text-white",
  needs_input: "border-amber-400 bg-amber-400 text-white",
  skipped: "border-border bg-muted text-muted-foreground/50",
};

function StatusGlyph({ status, Icon }: { status: TimelineStatus; Icon: LucideIcon }) {
  if (status === "active") return <Loader2 className="size-4 animate-spin" />;
  if (status === "completed") return <Check className="size-4" strokeWidth={3} />;
  if (status === "failed") return <X className="size-4" strokeWidth={3} />;
  if (status === "needs_input") return <CircleHelp className="size-4" strokeWidth={2.5} />;
  if (status === "skipped") return <Minus className="size-4" />;
  return <Icon className="size-4" />;
}

export function ExecutionTimeline({ items }: { items: TimelineItem[] }) {
  return (
    <ol className="relative space-y-1" aria-label="AI execution timeline">
      {items.map((item, i) => {
        const meta = STEP_META[item.key] ?? STEP_META.parse_request;
        const last = i === items.length - 1;
        const dim = item.status === "pending" || item.status === "skipped";
        return (
          <li key={item.key} className="relative flex gap-3.5 pb-3.5 last:pb-0">
            {!last && (
              <span
                className={cn(
                  "absolute left-[17px] top-9 h-[calc(100%-28px)] w-px transition-colors duration-500",
                  item.status === "completed" ? "bg-emerald-300" : "bg-border"
                )}
              />
            )}
            <div className="relative">
              {item.status === "active" && (
                <span className="absolute inset-0 animate-ping rounded-full bg-primary/20" aria-hidden />
              )}
              <motion.div
                key={item.status}
                initial={{ scale: 0.8 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", stiffness: 420, damping: 18 }}
                className={cn(
                  "relative flex size-[34px] shrink-0 items-center justify-center rounded-full border-2 transition-colors",
                  RING[item.status]
                )}
              >
                <StatusGlyph status={item.status} Icon={meta.icon} />
              </motion.div>
            </div>
            <div className="min-w-0 flex-1 pt-1">
              <div className="flex items-center justify-between gap-3">
                <p className={cn("text-sm font-medium", dim ? "text-muted-foreground" : "text-foreground")}>
                  {item.title}
                </p>
                {item.timestamp && (
                  <span className="shrink-0 font-mono text-[11px] tabular-nums text-muted-foreground">
                    {timeOfDay(item.timestamp, true)}
                    {item.duration_ms != null && ` · ${item.duration_ms}ms`}
                  </span>
                )}
              </div>
              <p
                className={cn(
                  "mt-0.5 text-[13px] leading-snug",
                  item.status === "failed" ? "text-red-600" : item.status === "needs_input" ? "text-amber-600" : "text-muted-foreground"
                )}
              >
                {item.status === "active" ? "Working…" : item.description || meta.idle}
              </p>
              {item.tools && item.tools.length > 0 && item.status !== "pending" && item.status !== "active" && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {item.tools.map((t, idx) => (
                    <span
                      key={`${t}-${idx}`}
                      className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[10.5px] text-muted-foreground"
                    >
                      {t}()
                    </span>
                  ))}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
