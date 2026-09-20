"use client";

import { Fragment, useMemo, useState } from "react";
import Link from "next/link";
import { Activity as ActivityIcon2, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/hooks/use-api";
import { dayLabel, timeOfDay } from "@/lib/format";
import { ACTION_META, ActivityIcon } from "@/components/activity-feed";
import { Card, EmptyState, ErrorState, PageHeader, RowsSkeleton } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "orders", label: "Orders" },
  { id: "issues", label: "Rejected & clarifications" },
  { id: "info", label: "Stock checks" },
] as const;

export default function ActivityPage() {
  const activity = useApi(() => api.activity(150), [], { interval: 5000 });
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["id"]>("all");

  const items = useMemo(() => {
    const all = activity.data ?? [];
    if (filter === "orders") return all.filter((a) => a.order_id != null);
    if (filter === "issues") return all.filter((a) => a.status === "failed" || a.status === "needs_input");
    if (filter === "info") return all.filter((a) => a.status === "info");
    return all;
  }, [activity.data, filter]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="AI Activity"
        subtitle="Everything KirAI does autonomously, straight from the activity log."
        actions={
          <>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
              <span className="relative flex size-2">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-70" />
                <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
              </span>
              Live
            </span>
            <Button variant="outline" onClick={() => activity.refetch()} className="gap-2">
              <RefreshCw className={`size-4 ${activity.refreshing ? "animate-spin" : ""}`} /> Refresh
            </Button>
          </>
        }
      />

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            className={cn(
              "rounded-full border px-3.5 py-1.5 text-sm font-medium transition",
              filter === f.id ? "border-primary bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground"
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      <Card>
        {activity.loading ? (
          <RowsSkeleton rows={8} label="Loading activity..." />
        ) : activity.error && !activity.data ? (
          <ErrorState message={activity.error} onRetry={activity.reload} className="m-4 border-0" />
        ) : items.length === 0 ? (
          <EmptyState icon={ActivityIcon2} title="No activity to show" description="Process a customer request in the AI Operator and it will appear here." />
        ) : (
          <ol className="px-5 py-3">
            {items.map((a, i) => {
              const showDay = i === 0 || dayLabel(items[i - 1].created_at) !== dayLabel(a.created_at);
              return (
                <Fragment key={a.id}>
                  {showDay && (
                    <li className="pb-2 pt-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground first:pt-2">
                      {dayLabel(a.created_at)}
                    </li>
                  )}
                  <li className="relative flex gap-4 py-2.5">
                    {i < items.length - 1 && <span className="absolute left-[88px] top-11 h-[calc(100%-24px)] w-px bg-border" aria-hidden />}
                    <span className="w-[62px] shrink-0 pt-1.5 text-right font-mono text-[12.5px] tabular-nums text-muted-foreground">
                      {timeOfDay(a.created_at, true)}
                    </span>
                    <ActivityIcon action={a.action} status={a.status} className="relative z-10 ring-4 ring-card" />
                    <div className="min-w-0 flex-1 pt-1">
                      <p className="text-sm font-medium">
                        {a.message}
                        {a.order_id && (
                          <Link href={`/orders?open=${a.order_id}`} className="ml-2 rounded-md bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground hover:text-foreground">
                            Order #{a.order_id}
                          </Link>
                        )}
                      </p>
                      <p className="text-xs text-muted-foreground">{ACTION_META[a.action]?.label ?? a.action}</p>
                    </div>
                  </li>
                </Fragment>
              );
            })}
          </ol>
        )}
      </Card>
    </div>
  );
}
