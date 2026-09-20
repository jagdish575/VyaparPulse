"use client";

import { useState, type ReactNode } from "react";
import { CheckCircle2, Cpu, Database, Loader2, RotateCcw, Store, TriangleAlert, Wifi, XCircle } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/hooks/use-api";
import { inr } from "@/lib/format";
import { Card, CardHeader, ErrorState, PageHeader } from "@/components/shared";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import type { AiStatus } from "@/types";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b px-5 py-3.5 text-sm last:border-b-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{children}</span>
    </div>
  );
}

export default function SettingsPage() {
  const settings = useApi(() => api.settings(), []);
  const [test, setTest] = useState<AiStatus | null>(null);
  const [testing, setTesting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [resetting, setResetting] = useState(false);

  const runTest = async () => {
    setTesting(true);
    try {
      setTest(await api.aiStatus(true));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "We couldn't test the connection.");
    } finally {
      setTesting(false);
    }
  };

  const reset = async () => {
    setResetting(true);
    try {
      await api.resetDemo();
      toast.success("Demo reset successfully.", { description: "Orders cleared and inventory restored." });
      setConfirming(false);
      settings.refetch();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "We couldn't reset the demo data.");
    } finally {
      setResetting(false);
    }
  };

  const s = settings.data;

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" subtitle="Store details, AI configuration and demo controls." />

      {settings.error && !s ? (
        <ErrorState message={settings.error} onRetry={settings.reload} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title="Store Information" description="Business rules applied to every order" />
            {!s ? <Skeleton className="m-5 h-28" /> : (
              <>
                <Row label="Store name">{s.store.name}</Row>
                <Row label="Location">{s.store.location}</Row>
                <Row label="Delivery charge">{inr(s.store.delivery_charge)}</Row>
                <Row label="Free delivery above">{inr(s.store.free_delivery_above)}</Row>
              </>
            )}
          </Card>

          <Card>
            <CardHeader title="AI Configuration" description="Language understanding runs on EURI" />
            {!s ? <Skeleton className="m-5 h-28" /> : (
              <>
                <Row label="AI provider"><span className="inline-flex items-center gap-1.5"><Cpu className="size-4 text-primary" />{s.ai.provider}</span></Row>
                <Row label="Model">{s.ai.model}</Row>
                <Row label="API key">
                  {s.ai.configured ? (
                    <span className="inline-flex items-center gap-1.5 text-emerald-600"><CheckCircle2 className="size-4" />Configured on server</span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-amber-600"><TriangleAlert className="size-4" />Not set — using local parser</span>
                  )}
                </Row>
                <Row label="Connection status">
                  {test ? (
                    test.connected ? (
                      <span className="inline-flex items-center gap-1.5 text-emerald-600"><Wifi className="size-4" />Connected</span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-red-600"><XCircle className="size-4" />{test.configured ? "Unreachable" : "Not configured"}</span>
                    )
                  ) : (
                    <span className="text-muted-foreground">Not tested</span>
                  )}
                </Row>
                <div className="flex items-center justify-between gap-3 px-5 py-4">
                  <p className="text-xs text-muted-foreground">The API key never leaves the backend.</p>
                  <Button variant="outline" size="sm" onClick={runTest} disabled={testing} className="gap-2">
                    {testing ? <Loader2 className="size-4 animate-spin" /> : <Wifi className="size-4" />} Test connection
                  </Button>
                </div>
              </>
            )}
          </Card>

          <Card>
            <CardHeader title="Demo Controls" description="Get back to a clean, repeatable demo" />
            <div className="space-y-4 p-5">
              <p className="text-sm text-muted-foreground">
                Deletes all orders, order items and activity logs, restores every product to its seed stock and recreates the demo customers.
              </p>
              {confirming ? (
                <div className="flex flex-wrap items-center gap-2 rounded-xl border border-red-200 bg-red-50 p-3">
                  <p className="mr-auto text-sm font-medium text-red-800">Reset all demo data?</p>
                  <Button variant="outline" size="sm" onClick={() => setConfirming(false)} disabled={resetting}>Cancel</Button>
                  <Button size="sm" onClick={reset} disabled={resetting} className="gap-2 bg-red-600 text-white hover:bg-red-700">
                    {resetting && <Loader2 className="size-4 animate-spin" />} Yes, reset
                  </Button>
                </div>
              ) : (
                <Button variant="outline" onClick={() => setConfirming(true)} className="gap-2">
                  <RotateCcw className="size-4" /> Reset Demo Data
                </Button>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="Database" description="Source of truth for stock, prices and orders" />
            {!s ? <Skeleton className="m-5 h-28" /> : (
              <>
                <Row label="Engine"><span className="inline-flex items-center gap-1.5"><Database className="size-4 text-primary" />{s.database.engine}</span></Row>
                <Row label="Products">{s.database.products}</Row>
                <Row label="Customers">{s.database.customers}</Row>
                <Row label="Orders">{s.database.orders}</Row>
              </>
            )}
          </Card>
        </div>
      )}
      <p className="flex items-center gap-2 text-xs text-muted-foreground"><Store className="size-3.5" /> KirAI · Your Kirana Store, Operated by AI.</p>
    </div>
  );
}
