"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  Bell,
  Boxes,
  LayoutDashboard,
  Menu,
  Search,
  Settings,
  ShoppingBag,
  Sparkles,
  Users,
  type LucideIcon,
} from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Logo } from "@/components/logo";
import { ActivityIcon } from "@/components/activity-feed";
import { api } from "@/lib/api";
import { useApi } from "@/hooks/use-api";
import { cn } from "@/lib/utils";
import { timeAgo } from "@/lib/format";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

const NAV: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/operator", label: "AI Operator", icon: Sparkles },
  { href: "/orders", label: "Orders", icon: ShoppingBag },
  { href: "/inventory", label: "Inventory", icon: Boxes },
  { href: "/customers", label: "Customers", icon: Users },
  { href: "/activity", label: "Activity", icon: Activity },
  { href: "/settings", label: "Settings", icon: Settings },
];
const MOBILE_TABS = [NAV[0], NAV[1], NAV[2], NAV[3]];

const isActive = (pathname: string, href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

function NavLinks({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  return (
    <nav className="space-y-1" aria-label="Main">
      {NAV.map((item) => {
        const active = isActive(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] font-medium transition-colors",
              active ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            <item.icon className={cn("size-[18px]", active ? "text-primary" : "text-muted-foreground group-hover:text-foreground")} />
            {item.label}
            {item.href === "/operator" && (
              <span className="ml-auto rounded-md bg-gradient-to-r from-indigo-600 to-violet-500 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">AI</span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}

function StoreStatus() {
  const health = useApi(() => api.health(), [], { interval: 20000 });
  const online = health.data?.status === "ok";
  const offline = !health.data && !!health.error;
  return (
    <div className="rounded-xl border bg-muted/40 p-3.5">
      <div className="flex items-center gap-2 text-sm font-medium">
        <span className="relative flex size-2.5">
          {online && <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-60" />}
          <span className={cn("relative inline-flex size-2.5 rounded-full", online ? "bg-emerald-500" : offline ? "bg-red-500" : "bg-amber-400")} />
        </span>
        {online ? "AI Operator Online" : offline ? "Backend offline" : "Connecting…"}
      </div>
      <p className="mt-1 pl-[18px] text-xs text-muted-foreground">
        {online ? (health.data?.ai_configured ? "EURI configured" : "Local parser mode") : offline ? "Start the API server" : "Checking store status"}
      </p>
    </div>
  );
}

function Notifications() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const stats = useApi(() => api.dashboard(), [], { interval: 20000 });
  const inv = useApi(() => api.inventory(), [open], { enabled: open });
  const act = useApi(() => api.activity(4), [open], { enabled: open });
  const low = stats.data?.low_stock_count ?? 0;

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const lowProducts = (inv.data?.products ?? []).filter((p) => p.stock_status !== "in_stock").slice(0, 4);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative flex size-10 items-center justify-center rounded-xl border bg-card text-muted-foreground transition hover:text-foreground"
        aria-label="Notifications"
        aria-expanded={open}
      >
        <Bell className="size-[18px]" />
        {low > 0 && <span className="absolute right-2.5 top-2.5 size-2 rounded-full bg-amber-500 ring-2 ring-card" />}
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border bg-popover shadow-xl">
          <div className="border-b px-4 py-3 text-sm font-semibold">Notifications</div>
          <div className="max-h-[70vh] overflow-y-auto">
            <p className="px-4 pb-1 pt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Stock alerts</p>
            {inv.loading ? (
              <p className="px-4 py-3 text-sm text-muted-foreground">Checking inventory…</p>
            ) : lowProducts.length ? (
              lowProducts.map((p) => (
                <Link key={p.id} href="/inventory" onClick={() => setOpen(false)} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm transition hover:bg-muted">
                  <span className="truncate">{p.name}</span>
                  <span className={cn("shrink-0 text-xs font-medium", p.stock_status === "out_of_stock" ? "text-red-600" : "text-amber-600")}>
                    {p.stock_status === "out_of_stock" ? "Out of stock" : `${p.stock_quantity} left`}
                  </span>
                </Link>
              ))
            ) : (
              <p className="px-4 py-3 text-sm text-muted-foreground">Everything is well stocked.</p>
            )}
            <p className="px-4 pb-1 pt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Latest AI activity</p>
            {act.loading ? (
              <p className="px-4 py-3 text-sm text-muted-foreground">Loading…</p>
            ) : (act.data ?? []).length ? (
              (act.data ?? []).map((a) => (
                <Link key={a.id} href={a.order_id ? `/orders?open=${a.order_id}` : "/activity"} onClick={() => setOpen(false)} className="flex items-start gap-2.5 px-4 py-2.5 transition hover:bg-muted">
                  <ActivityIcon action={a.action} status={a.status} className="size-7" />
                  <span className="min-w-0 text-sm">
                    <span className="line-clamp-2">{a.message}</span>
                    <span className="text-xs text-muted-foreground">{timeAgo(a.created_at)}</span>
                  </span>
                </Link>
              ))
            ) : (
              <p className="px-4 py-3 text-sm text-muted-foreground">No activity yet.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [menu, setMenu] = useState(false);
  const [search, setSearch] = useState("");
  const current = NAV.find((n) => isActive(pathname, n.href));

  const submitSearch = () => {
    const q = search.trim();
    if (q) {
      router.push(`/inventory?q=${encodeURIComponent(q)}`);
      setSearch("");
    }
  };

  return (
    <div className="min-h-screen">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r bg-sidebar px-4 py-5 lg:flex">
        <Link href="/" className="px-2 pb-6" aria-label="KirAI home">
          <Logo />
        </Link>
        <NavLinks pathname={pathname} />
        <div className="mt-auto">
          <StoreStatus />
        </div>
      </aside>

      {/* Mobile nav sheet */}
      <Sheet open={menu} onOpenChange={setMenu}>
        <SheetContent side="left" showCloseButton={false} className="data-[side=left]:w-72 gap-0 p-4">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <SheetDescription className="sr-only">Main navigation</SheetDescription>
          <div className="px-2 pb-6 pt-1">
            <Logo />
          </div>
          <NavLinks pathname={pathname} onNavigate={() => setMenu(false)} />
          <div className="mt-auto">
            <StoreStatus />
          </div>
        </SheetContent>
      </Sheet>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur-md sm:px-6 lg:px-8">
          <button
            onClick={() => setMenu(true)}
            className="flex size-10 items-center justify-center rounded-xl border bg-card lg:hidden"
            aria-label="Open menu"
          >
            <Menu className="size-5" />
          </button>
          <div className="min-w-0 lg:hidden">
            <Logo showTagline={false} />
          </div>
          <h2 className="hidden text-[15px] font-semibold text-muted-foreground lg:block">{current?.label ?? "KirAI"}</h2>

          <div className="ml-auto flex items-center gap-3">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                submitSearch();
              }}
              className="relative hidden md:block"
              role="search"
            >
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search products…"
                className="h-10 w-64 rounded-xl border bg-card pl-9 pr-3 text-sm outline-none transition focus:border-primary/50 focus:ring-4 focus:ring-primary/10"
                aria-label="Search products"
              />
            </form>
            <Notifications />
            <div className="flex items-center gap-2.5 rounded-xl border bg-card py-1.5 pl-1.5 pr-3">
              <div className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-600 to-violet-500 text-xs font-semibold text-white">RS</div>
              <div className="hidden leading-tight sm:block">
                <p className="text-[13px] font-semibold">Rahul Sharma</p>
                <p className="text-[11px] text-muted-foreground">Sharma Kirana Store</p>
              </div>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1400px] px-4 pb-28 pt-6 sm:px-6 lg:px-8 lg:pb-12 lg:pt-8">{children}</main>
      </div>

      {/* Mobile bottom tabs */}
      <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t bg-card/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden" aria-label="Quick navigation">
        {MOBILE_TABS.map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <Link key={item.href} href={item.href} className={cn("flex flex-col items-center gap-1 py-2.5 text-[11px] font-medium", active ? "text-primary" : "text-muted-foreground")}>
              <item.icon className="size-5" />
              {item.label === "AI Operator" ? "Operator" : item.label}
            </Link>
          );
        })}
        <button onClick={() => setMenu(true)} className="flex flex-col items-center gap-1 py-2.5 text-[11px] font-medium text-muted-foreground">
          <Menu className="size-5" />
          More
        </button>
      </nav>
    </div>
  );
}
