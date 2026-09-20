"use client";

import { useState } from "react";
import { BadgeIndianRupee, CalendarClock, RefreshCw, Wallet } from "lucide-react";
import { api } from "@/lib/api";
import { funds, ledgerApi, type Invoice, type Payable } from "@/lib/ledger";
import { useApi } from "@/hooks/use-api";
import { dateTime } from "@/lib/format";
import { ErrorState, PageHeader, StatCard } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { LedgerEntryForm, fieldClass, paymentMethod, type EntryField } from "@/components/ledger-entry-form";

const amount: EntryField = { name: "amount", label: "Amount (₹)", type: "money" };
const description: EntryField = { name: "description", label: "Description" };
const dueDate: EntryField = { name: "due_date", label: "Due date", type: "date" };

function Pager({ offset, total, change }: { offset: number; total: number; change: (value: number) => void }) {
  return <div className="mt-4 flex items-center justify-between gap-3 text-sm">
    <Button variant="outline" disabled={offset === 0} onClick={() => change(Math.max(0, offset - 50))}>Previous</Button>
    <span>{total ? `${offset + 1}–${Math.min(offset + 50, total)} of ${total}` : "No entries"}</span>
    <Button variant="outline" disabled={offset + 50 >= total} onClick={() => change(offset + 50)}>Next</Button>
  </div>;
}

export default function LedgerPage() {
  const [version, setVersion] = useState(0);
  const [mode, setMode] = useState("sale");
  const [customer, setCustomer] = useState("");
  const [invoiceOffset, setInvoiceOffset] = useState(0);
  const [billOffset, setBillOffset] = useState(0);
  const [movementOffset, setMovementOffset] = useState(0);
  const [payment, setPayment] = useState<{ type: "invoices" | "payables"; record: Invoice | Payable } | null>(null);
  const [reminder, setReminder] = useState<{ id: number; text: string } | null>(null);
  const [notice, setNotice] = useState("");
  const customers = useApi(() => api.customers(), [version]);
  const summary = useApi(() => ledgerApi.summary(), [version]);
  const invoices = useApi(() => ledgerApi.invoices(customer, invoiceOffset), [version, customer, invoiceOffset]);
  const bills = useApi(() => ledgerApi.payables(billOffset), [version, billOffset]);
  const movements = useApi(() => ledgerApi.movements(movementOffset), [version, movementOffset]);
  const refresh = () => { setVersion(v => v + 1); setReminder(null); };
  const s = summary.data;
  const customerField: EntryField = { name: "customer_id", label: "Customer", options: (customers.data ?? []).map(c => ({ value: String(c.id), label: c.name })) };
  const forms: Record<string, { title: string; path: string; fields: EntryField[]; note: string }> = {
    sale: { title: "Record a sale", path: "/invoices", fields: [customerField, description, amount,
      { name: "received", label: "Received now (₹)", type: "money", initial: "0" }, { ...dueDate, optional: true }, paymentMethod,
      { name: "order_id", label: "Existing order number", type: "number", optional: true },
      { name: "kind", label: "Entry type", initial: "sale", options: [{ value: "sale", label: "New sale" }, { value: "opening_receivable", label: "Old unpaid balance" }] }],
      note: "For credit or partial payment, enter a due date. An old unpaid balance must have Received now = 0 and no order number. Linking an order records its payment terms once; it does not deduct stock again. Amount-only sales do not change inventory." },
    customer: { title: "Add a customer", path: "/customers", fields: [{ name: "name", label: "Name" }, { name: "phone", label: "Phone", type: "tel" }, { name: "address", label: "Address", optional: true }], note: "Create a customer before recording their first sale." },
    payable: { title: "Record supplier dues", path: "/payables", fields: [{ name: "supplier", label: "Supplier" }, description, amount, dueDate], note: "An unpaid obligation does not reduce available funds until you record a payment." },
    expense: { title: "Record an expense", path: "/expenses", fields: [description, amount, paymentMethod], note: "Record an actual payment such as transport, electricity, or rent." },
  };

  async function showReminder(id: number) {
    setNotice("");
    try { const result = await ledgerApi.reminder(id); setReminder({ id, text: result.text }); }
    catch (e) { setNotice(e instanceof Error ? e.message : "Could not generate a reminder."); }
  }

  async function copyReminder() {
    if (!reminder) return;
    try {
      // Fetch again so a collection made since preview is reflected in the copy.
      const latest = await ledgerApi.reminder(reminder.id);
      setReminder({ id: reminder.id, text: latest.text });
      await navigator.clipboard.writeText(latest.text);
      setNotice("Reminder copied. Review it before sharing with your customer.");
    } catch (e) { setNotice(e instanceof Error ? e.message : "Copy unavailable. Select and copy the reminder text."); }
  }

  return <div className="space-y-6">
    <PageHeader title="Store ledger" subtitle="Sales, customer dues, collections, and money available to your store."
      actions={<Button variant="outline" onClick={refresh}><RefreshCw className="mr-2 size-4" />Refresh</Button>} />
    {summary.error && <ErrorState message={summary.error} onRetry={summary.reload} />}
    {summary.loading && <p role="status">Loading ledger…</p>}
    {s && !s.configured && <LedgerEntryForm title="Set opening funds" path="/opening" fields={[amount]} onSaved={refresh}
      note="Enter the combined cash, UPI, and bank funds available immediately before your first ledger entry. Enter 0 if none. This opening amount is set once; existing order totals are not assumed to be cash." />}

    {s && <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Available funds" icon={Wallet} value={funds(s.available_paise)} hint="Cash + UPI + bank, after recorded outflows" />
        <StatCard label="Customer dues" icon={BadgeIndianRupee} value={funds(s.receivables_paise)} hint={`${funds(s.overdue_paise)} overdue`} tone="amber" />
        <StatCard label="Due in next 7 days" icon={CalendarClock} value={funds(s.upcoming_paise)} hint="Invoice due dates; collection is uncertain" />
        <StatCard label="Supplier dues" icon={CalendarClock} value={funds(s.supplier_due_paise)} hint={`Overdue + due through ${s.through_date}`} tone="violet" />
      </div>
      <section className={`rounded-xl border p-5 ${s.shortfall_paise ? "border-amber-300 bg-amber-50" : "bg-card"}`}>
        <h2 className="font-semibold">Plan your next payment</h2>
        {!s.configured ? <p className="mt-2 text-sm">Set opening funds to calculate available money and a possible shortfall.</p> : <>
          <p className="mt-2 text-sm">{s.shortfall_paise ? `You are ${funds(s.shortfall_paise)} short before customer collections.` : "Recorded funds cover the supplier obligations in this period."}
            {` Available: ${funds(s.available_paise)}. Supplier dues through ${s.through_date}: ${funds(s.supplier_due_paise)}.`}</p>
          {!!s.priorities.length && <div className="mt-3 space-y-2"><p className="text-sm font-medium">Follow up on these overdue invoices. Payment is not guaranteed.</p>
            {s.priorities.map(i => <button key={i.id} className="block text-left text-sm text-primary underline" onClick={() => void showReminder(i.id)}>
              {i.customer_name} · Invoice #{i.id} · {funds(i.outstanding_paise)} · due {i.due_date}
            </button>)}
          </div>}
        </>}
      </section>
      <p className="text-sm text-muted-foreground">{s.unrecorded_orders} orders have no financial record. Their payment status is unknown and their totals are excluded from this ledger.
        {s.started_at && ` Ledger started ${dateTime(s.started_at)}.`}</p>
    </>}

    {notice && <p role="status" className="rounded-lg border p-3 text-sm">{notice}</p>}
    {reminder && <section className="space-y-3 rounded-xl border bg-card p-5">
      <h2 className="font-semibold">Payment reminder draft</h2><p className="select-text whitespace-pre-wrap text-sm">{reminder.text}</p>
      <Button variant="outline" onClick={() => void copyReminder()}>Copy current reminder</Button>
      <p className="text-xs text-muted-foreground">Review and share yourself. No message is sent automatically.</p>
    </section>}

    {s?.configured && <section className="space-y-3">
      <div className="flex flex-wrap gap-2">{Object.entries(forms).map(([key, form]) => <Button key={key} variant={mode === key ? "default" : "outline"} onClick={() => setMode(key)}>{form.title}</Button>)}</div>
      {customers.error && <ErrorState message={customers.error} onRetry={customers.reload} />}
      <LedgerEntryForm key={mode} {...forms[mode]} onSaved={refresh} />
    </section>}

    {payment && <section id="record-payment" className="space-y-2">
      <Button variant="outline" onClick={() => setPayment(null)}>Close payment form</Button>
      <LedgerEntryForm key={`${payment.type}-${payment.record.id}`} title={`${payment.type === "invoices" ? "Collect" : "Pay supplier"} · #${payment.record.id}`}
        path={`/${payment.type}/${payment.record.id}/payments`} fields={[amount, paymentMethod]} onSaved={() => { setPayment(null); refresh(); }}
        note={`Remaining balance at selection: ${funds(payment.record.outstanding_paise)}. The server checks the latest balance before saving.`} />
    </section>}

    <section className="space-y-4 rounded-xl border bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-semibold">Customer invoices</h2>
        <label className="text-sm">Customer <select className={fieldClass} value={customer} onChange={e => { setCustomer(e.target.value); setInvoiceOffset(0); }}>
          <option value="">All customers</option>{customers.data?.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select></label>
      </div>
      {invoices.error && <ErrorState message={invoices.error} onRetry={invoices.reload} />}
      {invoices.loading ? <p role="status">Loading invoices…</p> : <div className="grid gap-3 md:grid-cols-2">
        {invoices.data?.entries.map(i => <article key={i.id} className="space-y-3 rounded-xl border p-4">
          <div className="flex justify-between gap-2"><h3 className="font-medium">{i.customer_name} · #{i.id}</h3><span className={i.status === "overdue" ? "text-sm text-red-700" : "text-sm text-muted-foreground"}>{i.status}</span></div>
          <p className="text-sm">{i.description}{i.kind === "opening_receivable" ? " · Old unpaid balance" : ""}{i.order_id ? ` · Order #${i.order_id}` : ""}</p>
          <p className="text-sm">Total {funds(i.total_paise)} · Received {funds(i.received_paise)}</p>
          <p className="font-medium">Outstanding {funds(i.outstanding_paise)}</p>
          <p className="text-xs text-muted-foreground">{i.due_date ? `Due ${i.due_date}` : "Paid at sale"}</p>
          {i.outstanding_paise > 0 && <div className="flex flex-wrap gap-2">
            <Button onClick={() => { setPayment({ type: "invoices", record: i }); requestAnimationFrame(() => document.getElementById("record-payment")?.scrollIntoView({ behavior: "smooth" })); }}>Record collection</Button>
            <Button variant="outline" onClick={() => void showReminder(i.id)}>Reminder</Button>
          </div>}
        </article>)}
      </div>}
      <Pager offset={invoiceOffset} total={invoices.data?.total ?? 0} change={setInvoiceOffset} />
    </section>

    {customer && <CustomerLedger key={customer} customer={customer} version={version} />}

    <section className="space-y-4 rounded-xl border bg-card p-5">
      <h2 className="font-semibold">Supplier obligations</h2>
      {bills.error && <ErrorState message={bills.error} onRetry={bills.reload} />}
      {bills.loading ? <p role="status">Loading supplier dues…</p> : bills.data?.entries.map(b => <article key={b.id} className="flex flex-wrap items-center justify-between gap-4 rounded-lg border p-4">
        <div><h3 className="font-medium">{b.supplier} · #{b.id}</h3><p className="text-sm">{b.description}</p>
          <p className="text-sm">{funds(b.outstanding_paise)} remaining · Due {b.due_date} · {b.status}</p></div>
        {b.outstanding_paise > 0 && <Button variant="outline" onClick={() => { setPayment({ type: "payables", record: b }); requestAnimationFrame(() => document.getElementById("record-payment")?.scrollIntoView({ behavior: "smooth" })); }}>Record payment</Button>}
      </article>)}
      <Pager offset={billOffset} total={bills.data?.total ?? 0} change={setBillOffset} />
    </section>

    <section className="space-y-4 rounded-xl border bg-card p-5">
      <h2 className="font-semibold">Actual money movements</h2>
      {movements.error && <ErrorState message={movements.error} onRetry={movements.reload} />}
      {movements.loading ? <p role="status">Loading movements…</p> : movements.data?.entries.map(m => <div key={m.id} className="flex items-start justify-between gap-3 border-b pb-3 text-sm">
        <div><p>{m.description}</p><p className="text-xs text-muted-foreground">{m.method.toUpperCase()} · {dateTime(m.created_at)}</p></div>
        <p className={m.amount_paise > 0 ? "text-emerald-700" : "text-red-700"}>{funds(m.amount_paise)}</p>
      </div>)}
      <Pager offset={movementOffset} total={movements.data?.total ?? 0} change={setMovementOffset} />
    </section>
  </div>;
}

function CustomerLedger({ customer, version }: { customer: string; version: number }) {
  const [offset, setOffset] = useState(0);
  const ledger = useApi(() => ledgerApi.customer(customer, offset), [customer, offset, version]);
  return <section className="space-y-4 rounded-xl border bg-card p-5">
    <h2 className="font-semibold">Customer running ledger</h2>
    {ledger.error && <ErrorState message={ledger.error} onRetry={ledger.reload} />}
    {ledger.loading ? <p role="status">Loading history…</p> : <>
      <p>{ledger.data?.customer_name} · Outstanding {funds(ledger.data?.balance_paise)}</p>
      {ledger.data?.entries.map(e => <div key={e.id} className="flex flex-wrap justify-between gap-3 border-b pb-3 text-sm">
        <div><p>{e.description}</p><p className="text-xs text-muted-foreground">Invoice #{e.invoice_id} · {dateTime(e.created_at)}</p></div>
        <p>{funds(e.amount_paise)} · Balance {funds(e.balance_paise)}</p>
      </div>)}
    </>}
    <Pager offset={offset} total={ledger.data?.total ?? 0} change={setOffset} />
  </section>;
}
