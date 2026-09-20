"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { ledgerApi } from "@/lib/ledger";
import { Button } from "@/components/ui/button";

export interface EntryField {
  name: string;
  label: string;
  type?: "text" | "money" | "date" | "number" | "tel";
  optional?: boolean;
  options?: { value: string; label: string }[];
  initial?: string;
}

interface Draft {
  values: Record<string, string>;
  pending?: { key: string; body: Record<string, unknown> };
}

export const fieldClass = "h-11 w-full rounded-lg border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30";
export const paymentMethod: EntryField = { name: "method", label: "Payment method", initial: "cash", options: [
  { value: "cash", label: "Cash" }, { value: "upi", label: "UPI" }, { value: "bank", label: "Bank" },
] };

export function LedgerEntryForm({ title, path, fields, onSaved, note }: {
  title: string; path: string; fields: EntryField[]; onSaved: () => void; note?: string;
}) {
  const defaults = Object.fromEntries(fields.map(f => [f.name, f.initial ?? ""]));
  const [draft, setDraft] = useState<Draft>({ values: defaults });
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [storageWarning, setStorageWarning] = useState(false);
  const inFlight = useRef(false);
  const storageKey = `vyaparpulse:ledger:v1:${path}`;

  useEffect(() => {
    let alive = true;
    // Browser-only draft restoration runs after hydration.
    queueMicrotask(() => {
      if (!alive) return;
      try {
        const stored = localStorage.getItem(storageKey);
        if (stored) {
          const saved: Draft = JSON.parse(stored);
          if (saved.values && typeof saved.values === "object") setDraft(saved);
        }
      } catch { setStorageWarning(true); }
      setReady(true);
    });
    return () => { alive = false; };
  }, [storageKey]);

  function persist(next: Draft) {
    setDraft(next);
    try { localStorage.setItem(storageKey, JSON.stringify(next)); }
    catch { setStorageWarning(true); }
  }

  async function save() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    setMessage("");
    let pending = draft.pending;
    try {
      if (!pending) {
        const body: Record<string, unknown> = {};
        for (const field of fields) {
          const value = (draft.values[field.name] ?? "").trim();
          if (!value && field.optional) continue;
          body[field.name] = field.type === "number" || field.name === "customer_id" ? Number(value) : value;
        }
        pending = { key: crypto.randomUUID(), body };
        persist({ ...draft, pending });
      }
      await ledgerApi.save(path, pending.body, pending.key);
      try { localStorage.removeItem(storageKey); } catch { setStorageWarning(true); }
      setDraft({ values: defaults });
      setMessage("Saved to the ledger.");
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save this entry.");
      // Definite request rejection permits editing. Network/server failures retain
      // the exact body/key so an uncertain committed request can be safely replayed.
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) persist({ values: draft.values });
    } finally { inFlight.current = false; setBusy(false); }
  }

  return (
    <form className="space-y-4 rounded-xl border bg-card p-5" onSubmit={e => { e.preventDefault(); void save(); }}>
      <div><h2 className="font-semibold">{title}</h2>{note && <p className="mt-1 text-sm text-muted-foreground">{note}</p>}</div>
      <fieldset disabled={busy || !ready || !!draft.pending} className="grid gap-4 sm:grid-cols-2 disabled:opacity-70">
        {fields.map(field => (
          <label key={field.name} className="space-y-1.5 text-sm">
            <span>{field.label}{field.optional ? " (optional)" : ""}</span>
            {field.options ? (
              <select className={fieldClass} required={!field.optional} value={draft.values[field.name] ?? ""}
                onChange={e => { persist({ values: { ...draft.values, [field.name]: e.target.value } }); setMessage(""); }}>
                {!field.initial && <option value="">Select…</option>}
                {field.options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            ) : (
              <input className={fieldClass} required={!field.optional}
                type={field.type === "money" ? "text" : field.type ?? "text"}
                inputMode={field.type === "money" ? "decimal" : undefined}
                pattern={field.type === "money" ? "[0-9]+([.][0-9]{1,2})?" : undefined}
                min={field.type === "number" ? 1 : undefined}
                maxLength={field.type === "money" ? 12 : field.name === "phone" ? 16 : field.name === "name" || field.name === "supplier" ? 120 : 255}
                value={draft.values[field.name] ?? ""}
                onChange={e => { persist({ values: { ...draft.values, [field.name]: e.target.value } }); setMessage(""); }} />
            )}
          </label>
        ))}
      </fieldset>
      {storageWarning && <p className="text-sm text-amber-700">Browser storage is unavailable. Keep this page open until the save is confirmed.</p>}
      {draft.pending && !busy && <p className="text-sm text-amber-700">The previous save is not yet confirmed. Retry safely with the same details before creating another entry.</p>}
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      {message && <p role="status" className="text-sm text-emerald-700">{message}</p>}
      <Button type="submit" disabled={busy || !ready}>{busy ? "Saving…" : draft.pending ? "Retry save safely" : "Save entry"}</Button>
      {!message && !draft.pending && <p className="text-xs text-muted-foreground">Unsubmitted drafts stay in this browser. Entries save online.</p>}
    </form>
  );
}
