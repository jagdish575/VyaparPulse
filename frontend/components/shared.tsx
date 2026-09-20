"use client";

import type { ReactNode } from "react";
import { ArrowDownRight, ArrowUpRight, Inbox, RotateCcw, TriangleAlert, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { STATUS_LABEL } from "@/lib/format";
import type { StockStatus } from "@/types";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-[26px] font-semibold tracking-tight text-foreground sm:text-[28px]">{title}</h1>
        {subtitle && <p className="mt-1 text-[15px] text-muted-foreground">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

const TONES = {
  indigo: "bg-indigo-50 text-indigo-600",
  emerald: "bg-emerald-50 text-emerald-600",
  amber: "bg-amber-50 text-amber-600",
  violet: "bg-violet-50 text-violet-600",
  red: "bg-red-50 text-red-600",
  sky: "bg-sky-50 text-sky-600",
} as const;

export function StatCard({
  label,
  value,
  icon: Icon,
  tone = "indigo",
  trend,
  hint,
  loading,
}: {
  label: string;
  value: ReactNode;
  icon: LucideIcon;
  tone?: keyof typeof TONES;
  /** Percent change vs previous period; null/undefined hides the chip. */
  trend?: number | null;
  hint?: ReactNode;
  loading?: boolean;
}) {
  return (
    <div className="rounded-2xl border bg-card p-5 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between">
        <p className="text-sm font-medium text-muted-foreground">{label}</p>
        <div className={cn("flex size-9 items-center justify-center rounded-xl", TONES[tone])}>
          <Icon className="size-[18px]" />
        </div>
      </div>
      {loading ? (
        <>
          <Skeleton className="mt-3 h-8 w-24" />
          <Skeleton className="mt-3 h-4 w-32" />
        </>
      ) : (
        <>
          <p className="mt-2 text-[30px] font-semibold leading-tight tracking-tight tabular-nums">{value}</p>
          <div className="mt-1.5 flex items-center gap-2 text-[13px] text-muted-foreground">
            {trend != null && (
              <span
                className={cn(
                  "inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-xs font-medium",
                  trend >= 0 ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
                )}
              >
                {trend >= 0 ? <ArrowUpRight className="size-3" /> : <ArrowDownRight className="size-3" />}
                {Math.abs(trend)}%
              </span>
            )}
            {hint && <span>{hint}</span>}
          </div>
        </>
      )}
    </div>
  );
}

const STOCK_STYLE: Record<StockStatus, { label: string; cls: string; dot: string }> = {
  in_stock: { label: "In Stock", cls: "bg-emerald-50 text-emerald-700 ring-emerald-600/15", dot: "bg-emerald-500" },
  low_stock: { label: "Low Stock", cls: "bg-amber-50 text-amber-700 ring-amber-600/20", dot: "bg-amber-500" },
  out_of_stock: { label: "Out of Stock", cls: "bg-red-50 text-red-700 ring-red-600/15", dot: "bg-red-500" },
};

export function StockBadge({ status, quantity, compact }: { status: StockStatus; quantity?: number; compact?: boolean }) {
  const s = STOCK_STYLE[status];
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
        s.cls
      )}
    >
      <span className={cn("size-1.5 rounded-full", s.dot)} />
      {compact && quantity != null && status !== "out_of_stock" ? `${quantity} left` : s.label}
    </span>
  );
}

/** Visual stock level: ████████ 32 */
export function StockBar({ quantity, threshold, status }: { quantity: number; threshold: number; status: StockStatus }) {
  const pct = Math.max(quantity > 0 ? 6 : 0, Math.min(100, (quantity / Math.max(threshold * 4, 1)) * 100));
  const color = status === "in_stock" ? "bg-emerald-500" : status === "low_stock" ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-3">
      <div className="h-2 w-28 overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full transition-all duration-700", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-8 text-sm font-medium tabular-nums">{quantity}</span>
    </div>
  );
}

const ORDER_STYLE: Record<string, string> = {
  confirmed: "bg-indigo-50 text-indigo-700 ring-indigo-600/15",
  out_for_delivery: "bg-amber-50 text-amber-700 ring-amber-600/20",
  delivered: "bg-emerald-50 text-emerald-700 ring-emerald-600/15",
  cancelled: "bg-zinc-100 text-zinc-600 ring-zinc-500/20",
};

export function OrderStatusBadge({ status }: { status: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
        ORDER_STYLE[status] ?? ORDER_STYLE.confirmed
      )}
    >
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

export function SourceBadge({ source }: { source: string }) {
  if (source === "ai_agent")
    return (
      <span className="inline-flex items-center rounded-md bg-gradient-to-r from-indigo-50 to-violet-50 px-1.5 py-0.5 text-[11px] font-medium text-violet-700 ring-1 ring-inset ring-violet-500/20">
        KirAI
      </span>
    );
  return (
    <span className="inline-flex items-center rounded-md bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
      {source === "seed" ? "Sample data" : "Manual"}
    </span>
  );
}

export function ErrorState({ message, onRetry, className }: { message: string; onRetry?: () => void; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed bg-card px-6 py-12 text-center", className)}>
      <div className="flex size-11 items-center justify-center rounded-full bg-red-50 text-red-600">
        <TriangleAlert className="size-5" />
      </div>
      <div>
        <p className="font-medium">Something went wrong</p>
        <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">{message}</p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="inline-flex items-center gap-2 rounded-lg border bg-background px-3.5 py-2 text-sm font-medium shadow-xs transition hover:bg-muted"
        >
          <RotateCcw className="size-4" /> Try Again
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, description, icon: Icon = Inbox }: { title: string; description?: string; icon?: LucideIcon }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      <div className="flex size-11 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Icon className="size-5" />
      </div>
      <p className="font-medium">{title}</p>
      {description && <p className="max-w-sm text-sm text-muted-foreground">{description}</p>}
    </div>
  );
}

export function RowsSkeleton({ rows = 6, label }: { rows?: number; label?: string }) {
  return (
    <div className="divide-y" role="status" aria-label={label ?? "Loading"}>
      {label && <p className="px-5 py-3 text-sm text-muted-foreground">{label}</p>}
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-5 py-4">
          <Skeleton className="size-9 rounded-lg" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-3 w-1/4" />
          </div>
          <Skeleton className="h-6 w-20 rounded-full" />
        </div>
      ))}
    </div>
  );
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("rounded-2xl border bg-card shadow-sm", className)}>{children}</div>;
}

export function CardHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b px-5 py-4">
      <div>
        <h2 className="text-[15px] font-semibold leading-tight">{title}</h2>
        {description && <p className="mt-0.5 text-[13px] text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  );
}
