"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, ArrowUp, Cpu, RotateCcw, Sparkles, Store, User, Wand2, Zap } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useApi } from "@/hooks/use-api";
import { cn } from "@/lib/utils";
import { inr } from "@/lib/format";
import { ExecutionTimeline, PIPELINE, STEP_META, type TimelineItem } from "@/components/operator/timeline";
import { OrderConfirmationCard } from "@/components/operator/order-card";
import { StockBadge } from "@/components/shared";
import type { AgentOrder, AgentResponse, Draft, ProductCard } from "@/types";

const DEMO_MESSAGE =
  "Bhaiya 2 packets Aashirvaad atta, 1 Fortune oil aur 3 Maggi bhej do. Ghar pe deliver kar dena.";
const QUICK_COMMANDS = ["Order 2 Maggi", "Check atta stock", "Show low stock"];
const STEP_DELAY_MS = 320;

interface ChatMsg {
  id: string;
  role: "user" | "ai";
  text: string;
  response?: AgentResponse;
  error?: boolean;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const uid = () => Math.random().toString(36).slice(2, 10);

const WELCOME: ChatMsg = {
  id: "welcome",
  role: "ai",
  text: "Namaste! I'm KirAI. Tell me what your customer needs in English or Hinglish — I'll check the live inventory, price it from the database and place the order.",
};

function idleTimeline(): TimelineItem[] {
  return PIPELINE.map((s) => ({ key: s.key, title: s.title, description: STEP_META[s.key].idle, status: "pending" }));
}

export function OperatorConsole() {
  const params = useSearchParams();
  const { data: customers } = useApi(() => api.customers(), []);
  const [customerId, setCustomerId] = useState(1);
  const customer = customers?.find((c) => c.id === customerId);

  const [messages, setMessages] = useState<ChatMsg[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [timeline, setTimeline] = useState<TimelineItem[]>(idleTimeline);
  const [last, setLast] = useState<AgentResponse | null>(null);
  const [order, setOrder] = useState<AgentOrder | null>(null);
  const [showInventory, setShowInventory] = useState(false);
  const [elapsed, setElapsed] = useState<number | null>(null);

  const draftRef = useRef<Draft | null>(null);
  const runRef = useRef(0);
  const scroller = useRef<HTMLDivElement>(null);
  const timelineScroller = useRef<HTMLDivElement>(null);
  const autoSent = useRef(false);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  // Keep the step that is currently running in view if the timeline is taller than its panel.
  useEffect(() => {
    const el = timelineScroller.current;
    if (el && timeline.some((t) => t.status === "active")) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [timeline]);

  const reveal = useCallback(async (res: AgentResponse, run: number) => {
    const items: TimelineItem[] = res.steps.map((s) => ({
      key: s.name,
      title: s.title,
      description: "",
      status: "pending",
    }));
    setTimeline(items);
    for (let i = 0; i < res.steps.length; i++) {
      if (runRef.current !== run) return;
      setTimeline((prev) => prev.map((it, idx) => (idx === i ? { ...it, status: "active" } : it)));
      await sleep(STEP_DELAY_MS);
      if (runRef.current !== run) return;
      const s = res.steps[i];
      setTimeline((prev) =>
        prev.map((it, idx) =>
          idx === i
            ? { ...it, status: s.status, description: s.message, timestamp: s.timestamp, duration_ms: s.duration_ms, tools: s.tools }
            : it
        )
      );
    }
  }, []);

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || busy) return;
      const run = ++runRef.current;
      const startedAt = performance.now();
      setMessages((m) => [...m, { id: uid(), role: "user", text }]);
      setInput("");
      setBusy(true);
      setOrder(null);
      setShowInventory(false);
      setElapsed(null);
      setLast(null);
      setTimeline(
        PIPELINE.map((s, i) => ({
          key: s.key,
          title: s.title,
          description: STEP_META[s.key].idle,
          status: i === 0 ? "active" : "pending",
        }))
      );
      try {
        const res = await api.process({
          message: text,
          customer_id: customerId,
          delivery_address: customer?.address,
          draft: draftRef.current,
        });
        if (runRef.current !== run) return;
        await reveal(res, run);
        if (runRef.current !== run) return;

        draftRef.current = res.draft;
        setLast(res);
        setElapsed(Math.round(performance.now() - startedAt));
        setMessages((m) => [...m, { id: uid(), role: "ai", text: res.reply, response: res }]);

        if (res.order) {
          setOrder(res.order);
          toast.success("Order created successfully.", { description: `Order #${res.order.id} · ${inr(res.order.total)}` });
          setTimeout(() => {
            if (runRef.current === run) {
              setShowInventory(true);
              toast.success("Inventory updated.");
            }
          }, 700);
        }
      } catch (e) {
        if (runRef.current !== run) return;
        const message = e instanceof Error && e.message ? e.message : "Something went wrong while processing your request.";
        setTimeline(idleTimeline());
        setMessages((m) => [...m, { id: uid(), role: "ai", text: message, error: true }]);
        toast.error("We couldn't process that request.");
      } finally {
        if (runRef.current === run) setBusy(false);
      }
    },
    [busy, customer?.address, customerId, reveal]
  );

  // Quick AI command from the dashboard: /operator?q=...
  useEffect(() => {
    const q = params.get("q");
    if (q && !autoSent.current && customers) {
      autoSent.current = true;
      send(q);
    }
  }, [params, customers, send]);

  const resetChat = () => {
    runRef.current++;
    draftRef.current = null;
    setMessages([WELCOME]);
    setTimeline(idleTimeline());
    setOrder(null);
    setLast(null);
    setBusy(false);
    setElapsed(null);
  };

  const lastFailed = useMemo(() => messages[messages.length - 1]?.error, [messages]);
  const lastUser = useMemo(() => [...messages].reverse().find((m) => m.role === "user")?.text, [messages]);

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        {/* ------------------------------------------------------------ customer request panel */}
        <section className="flex h-[680px] flex-col overflow-hidden rounded-2xl border bg-card shadow-sm xl:h-[740px]">
          <header className="flex items-center justify-between gap-3 border-b px-5 py-3.5">
            <div className="flex items-center gap-3">
              <div className="flex size-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-600 to-violet-500 text-white shadow-sm">
                <Sparkles className="size-[18px]" />
              </div>
              <div>
                <h2 className="text-[15px] font-semibold leading-tight">AI Store Operator</h2>
                <p className="flex items-center gap-1.5 text-xs text-emerald-600">
                  <span className="relative flex size-2">
                    <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-70" />
                    <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
                  </span>
                  Online
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <label className="sr-only" htmlFor="customer">Customer</label>
              <div className="flex items-center gap-1.5 rounded-lg border bg-background px-2 py-1 text-xs text-muted-foreground">
                <User className="size-3.5" />
                <select
                  id="customer"
                  value={customerId}
                  onChange={(e) => {
                    draftRef.current = null;
                    setCustomerId(Number(e.target.value));
                  }}
                  disabled={busy}
                  className="max-w-[9.5rem] truncate bg-transparent text-xs font-medium text-foreground outline-none"
                >
                  {(customers ?? [{ id: 1, name: "Rahul Sharma" }]).map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
              <button
                onClick={resetChat}
                title="Clear conversation"
                className="rounded-lg border p-1.5 text-muted-foreground transition hover:bg-muted hover:text-foreground"
              >
                <RotateCcw className="size-3.5" />
              </button>
            </div>
          </header>

          <div ref={scroller} className="flex-1 space-y-4 overflow-y-auto bg-[radial-gradient(60%_50%_at_50%_0%,rgba(99,102,241,0.05),transparent)] px-4 py-5 sm:px-5">
            {messages.map((m) => (
              <ChatBubble key={m.id} msg={m} onPick={(t) => send(t)} disabled={busy} />
            ))}
            {busy && (
              <div className="flex items-end gap-2.5">
                <AiAvatar />
                <div className="flex items-center gap-1 rounded-2xl rounded-bl-md border bg-card px-4 py-3">
                  {[0, 1, 2].map((i) => (
                    <motion.span
                      key={i}
                      className="size-1.5 rounded-full bg-primary/60"
                      animate={{ opacity: [0.3, 1, 0.3], y: [0, -2, 0] }}
                      transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.15 }}
                    />
                  ))}
                  <span className="ml-2 text-xs text-muted-foreground">Processing AI request…</span>
                </div>
              </div>
            )}
            {lastFailed && !busy && lastUser && (
              <div className="flex justify-center">
                <button
                  onClick={() => send(lastUser)}
                  className="inline-flex items-center gap-1.5 rounded-lg border bg-card px-3 py-1.5 text-xs font-medium hover:bg-muted"
                >
                  <RotateCcw className="size-3.5" /> Try Again
                </button>
              </div>
            )}
          </div>

          <div className="space-y-3 border-t bg-card px-4 py-3.5 sm:px-5">
            <div className="flex flex-wrap gap-1.5">
              <button
                disabled={busy}
                onClick={() => setInput(DEMO_MESSAGE)}
                className="inline-flex items-center gap-1.5 rounded-full border border-primary/25 bg-primary/5 px-3 py-1 text-xs font-medium text-primary transition hover:bg-primary/10 disabled:opacity-50"
              >
                <Wand2 className="size-3" /> Use demo request
              </button>
              {QUICK_COMMANDS.map((q) => (
                <button
                  key={q}
                  disabled={busy}
                  onClick={() => send(q)}
                  className="rounded-full border bg-background px-3 py-1 text-xs font-medium text-muted-foreground transition hover:border-primary/40 hover:text-foreground disabled:opacity-50"
                >
                  {q}
                </button>
              ))}
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                send(input);
              }}
              className="flex items-center gap-2 rounded-xl border bg-background p-1.5 pl-3.5 shadow-xs transition focus-within:border-primary/50 focus-within:ring-4 focus-within:ring-primary/10"
            >
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Tell KirAI what your customer needs..."
                disabled={busy}
                maxLength={600}
                className="min-w-0 flex-1 bg-transparent py-2 text-[15px] outline-none placeholder:text-muted-foreground/70"
                aria-label="Customer request"
              />
              <button
                type="submit"
                disabled={busy || !input.trim()}
                className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-600 to-violet-500 text-white shadow-sm transition hover:brightness-110 disabled:opacity-40"
                aria-label="Send"
              >
                <ArrowUp className="size-[18px]" />
              </button>
            </form>
          </div>
        </section>

        {/* ------------------------------------------------------------ AI execution panel */}
        <section className="flex h-[680px] flex-col overflow-hidden rounded-2xl border bg-card shadow-sm xl:h-[740px]">
          <header className="flex items-center justify-between gap-3 border-b px-5 py-3.5">
            <div>
              <h2 className="text-[15px] font-semibold leading-tight">AI Activity</h2>
              <p className="text-xs text-muted-foreground">
                {busy ? "Executing against the live database…" : last ? "Every step below ran on the backend" : "Send a request to watch KirAI work"}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {elapsed != null && !busy && (
                <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-xs font-medium tabular-nums text-muted-foreground">
                  <Zap className="size-3" /> {(elapsed / 1000).toFixed(1)}s
                </span>
              )}
            </div>
          </header>

          <div ref={timelineScroller} className="flex-1 overflow-y-auto px-5 py-5">
            <ExecutionTimeline items={timeline} />
          </div>

          <footer className="border-t bg-muted/30 px-5 py-3">
            <ParserBadge response={last} busy={busy} />
          </footer>
        </section>
      </div>

      <AnimatePresence>
        {order && (
          <motion.div key={order.id} exit={{ opacity: 0 }}>
            <OrderConfirmationCard order={order} showInventory={showInventory} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function AiAvatar() {
  return (
    <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-600 to-violet-500 text-white">
      <Sparkles className="size-3.5" />
    </div>
  );
}

function ParserBadge({ response, busy }: { response: AgentResponse | null; busy: boolean }) {
  if (busy || !response?.parser) {
    return (
      <p className="flex items-center gap-2 text-xs text-muted-foreground">
        <Store className="size-3.5" /> Prices, stock and order ids always come from the store database.
      </p>
    );
  }
  const p = response.parser;
  return (
    <div className="flex items-start gap-2 text-xs">
      {p.provider === "euri" ? (
        <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 font-medium text-primary">
          <Cpu className="size-3" /> Understood by EURI · {p.model}
        </span>
      ) : (
        <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-amber-100 px-2.5 py-1 font-medium text-amber-700">
          <AlertTriangle className="size-3" /> Local parser
        </span>
      )}
      <span className="pt-1 text-muted-foreground">
        {p.provider === "euri" ? "Language understanding via EURI; everything else from the database." : p.note}
      </span>
    </div>
  );
}

function ChatBubble({ msg, onPick, disabled }: { msg: ChatMsg; onPick: (text: string) => void; disabled: boolean }) {
  if (msg.role === "user") {
    return (
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-gradient-to-br from-indigo-600 to-violet-600 px-4 py-2.5 text-[15px] leading-relaxed text-white shadow-sm">
          {msg.text}
        </div>
      </motion.div>
    );
  }
  const res = msg.response;
  const warn = res && (res.status === "rejected" || res.status === "needs_input");
  const success = res?.status === "confirmed";
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex items-end gap-2.5">
      <AiAvatar />
      <div className="max-w-[88%] space-y-2.5">
        <div
          className={cn(
            "whitespace-pre-line rounded-2xl rounded-bl-md border px-4 py-2.5 text-[15px] leading-relaxed",
            msg.error && "border-red-200 bg-red-50 text-red-800",
            warn && "border-amber-200 bg-amber-50/70",
            success && "border-emerald-200 bg-emerald-50/60",
            !msg.error && !warn && !success && "bg-card"
          )}
        >
          {msg.text}
        </div>

        {res?.clarification && (
          <div className="grid gap-2 sm:grid-cols-2">
            {res.clarification.options.map((o, i) => (
              <button
                key={o.product_id}
                disabled={disabled}
                onClick={() => onPick(o.name)}
                className="group flex items-center justify-between gap-3 rounded-xl border bg-card px-3.5 py-2.5 text-left transition hover:border-primary/50 hover:bg-primary/5 disabled:opacity-50"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">
                    {i + 1}. {o.name}
                  </span>
                  <span className="text-xs text-muted-foreground">{inr(o.price)} · {o.stock_quantity} in stock</span>
                </span>
                <ArrowUp className="size-4 rotate-45 text-muted-foreground transition group-hover:text-primary" />
              </button>
            ))}
          </div>
        )}

        {res && res.products.length > 0 && !res.clarification && (
          <ProductList products={res.products} onPick={res.status === "rejected" ? onPick : undefined} disabled={disabled} />
        )}
      </div>
    </motion.div>
  );
}

function ProductList({
  products,
  onPick,
  disabled,
}: {
  products: ProductCard[];
  onPick?: (text: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {products.map((p) => {
        const Body = (
          <>
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium">{p.name}</span>
              <span className="text-xs text-muted-foreground">{inr(p.price)} per {p.unit}</span>
            </span>
            <StockBadge status={p.stock_status} quantity={p.stock_quantity} compact />
          </>
        );
        return onPick ? (
          <button
            key={p.id}
            disabled={disabled || p.stock_status === "out_of_stock"}
            onClick={() => onPick(`1 ${p.name}`)}
            className="flex items-center justify-between gap-3 rounded-xl border bg-card px-3.5 py-2.5 text-left transition hover:border-primary/50 hover:bg-primary/5 disabled:opacity-60"
          >
            {Body}
          </button>
        ) : (
          <div key={p.id} className="flex items-center justify-between gap-3 rounded-xl border bg-card px-3.5 py-2.5">
            {Body}
          </div>
        );
      })}
    </div>
  );
}
