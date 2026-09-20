"use client";

/**
 * Client-side session gate. This is a usability layer only: the API enforces access on every request
 * (private routes answer 401 without a valid session), so hiding a page here is never the security boundary.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2, RotateCcw, ServerOff } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { LogoMark } from "@/components/logo";
import { ApiError, UNAUTHORIZED_EVENT, authApi, clearLocalDrafts, type AuthStatus } from "@/lib/api";

type State =
  | { phase: "loading" }
  | { phase: "offline"; message: string }
  | { phase: "ready"; required: boolean; authenticated: boolean };

interface AuthContextValue {
  /** True when the store has an owner password (so a sign-out button makes sense). */
  required: boolean;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  required: false,
  refresh: async () => {},
  signOut: async () => {},
});
export const useAuth = () => useContext(AuthContext);

function FullScreen({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
      <LogoMark size={44} />
      {children}
    </div>
  );
}

const toReady = (me: AuthStatus): State => ({ phase: "ready", required: me.auth_required, authenticated: me.authenticated });
const toOffline = (e: unknown): State => ({
  phase: "offline",
  message: e instanceof ApiError ? e.message : "We couldn't reach the KirAI server.",
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [state, setState] = useState<State>({ phase: "loading" });

  const refresh = useCallback(async () => {
    try {
      setState(toReady(await authApi.me()));
    } catch (e) {
      setState(toOffline(e));
    }
  }, []);

  // Initial session check on mount (state is only set from the promise callbacks).
  useEffect(() => {
    let cancelled = false;
    authApi
      .me()
      .then((me) => !cancelled && setState(toReady(me)))
      .catch((e) => !cancelled && setState(toOffline(e)));
    return () => {
      cancelled = true;
    };
  }, []);

  // Any private request that comes back 401 (expired session) sends the owner to the login screen.
  useEffect(() => {
    const onUnauthorized = () =>
      setState((s) => (s.phase === "ready" && s.required ? { ...s, authenticated: false } : s));
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  const needsLogin = state.phase === "ready" && state.required && !state.authenticated;
  useEffect(() => {
    if (needsLogin && pathname !== "/login") {
      const next = pathname + (typeof window !== "undefined" ? window.location.search : "");
      router.replace(`/login?next=${encodeURIComponent(next)}`);
    }
  }, [needsLogin, pathname, router]);

  const signOut = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      /* the cookie is cleared server-side on the next request anyway */
    }
    clearLocalDrafts(); // unfinished forms may contain customer / financial details
    setState({ phase: "ready", required: true, authenticated: false });
    router.replace("/login");
  }, [router]);

  const value = useMemo<AuthContextValue>(
    () => ({ required: state.phase === "ready" && state.required, refresh, signOut }),
    [state, refresh, signOut]
  );

  let content: ReactNode;
  if (pathname === "/login") {
    content = children; // the login screen renders without the app chrome
  } else if (state.phase === "loading") {
    content = (
      <FullScreen>
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <Loader2 className="size-4 animate-spin" /> Checking your session…
        </p>
      </FullScreen>
    );
  } else if (state.phase === "offline") {
    content = (
      <FullScreen>
        <div className="flex size-11 items-center justify-center rounded-full bg-red-50 text-red-600">
          <ServerOff className="size-5" />
        </div>
        <div>
          <p className="font-medium">We can&apos;t reach KirAI</p>
          <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">{state.message}</p>
        </div>
        <button
          onClick={() => {
            setState({ phase: "loading" });
            void refresh();
          }}
          className="inline-flex items-center gap-2 rounded-lg border bg-background px-3.5 py-2 text-sm font-medium shadow-xs transition hover:bg-muted"
        >
          <RotateCcw className="size-4" /> Try Again
        </button>
      </FullScreen>
    );
  } else if (needsLogin) {
    content = (
      <FullScreen>
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <Loader2 className="size-4 animate-spin" /> Taking you to sign in…
        </p>
      </FullScreen>
    );
  } else {
    content = <AppShell>{children}</AppShell>;
  }

  return <AuthContext.Provider value={value}>{content}</AuthContext.Provider>;
}
