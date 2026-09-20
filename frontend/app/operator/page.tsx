import { Suspense } from "react";
import { OperatorConsole } from "@/components/operator/console";
import { PageHeader } from "@/components/shared";

export const metadata = { title: "AI Operator — KirAI" };

export default function OperatorPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="AI Operator"
        subtitle="Send a customer request and watch KirAI run the store — every step hits the real database."
      />
      <Suspense fallback={<div className="h-[640px] animate-pulse rounded-2xl border bg-card" />}>
        <OperatorConsole />
      </Suspense>
    </div>
  );
}
