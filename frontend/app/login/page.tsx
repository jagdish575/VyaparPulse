"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2, Lock } from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { LogoMark } from "@/components/logo";
import { ApiError, authApi } from "@/lib/api";

/** Only allow same-site relative paths after login (prevents open redirects). */
function safeNext(value: string | null): string {
  return value && value.startsWith("/") && !value.startsWith("//") && !value.startsWith("/login") ? value : "/";
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { refresh } = useAuth();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password || busy) return;
    setBusy(true);
    setError(null);
    try {
      await authApi.login(password);
      setPassword("");
      await refresh();
      router.replace(safeNext(params.get("next")));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "We couldn't sign you in. Please try again.");
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="w-full max-w-sm space-y-5 rounded-2xl border bg-card p-6 shadow-sm sm:p-8">
      <div className="flex flex-col items-center gap-3 text-center">
        <LogoMark size={48} />
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Sign in to KirAI</h1>
          <p className="mt-1 text-sm text-muted-foreground">Store owner access only.</p>
        </div>
      </div>

      <div className="space-y-2">
        <label htmlFor="password" className="text-sm font-medium">
          Password
        </label>
        <div className="relative">
          <Lock className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? "login-error" : undefined}
            className="h-11 w-full rounded-lg border bg-background pl-9 pr-3 text-[15px] outline-none transition focus:border-primary/50 focus:ring-4 focus:ring-primary/10"
          />
        </div>
        {error && (
          <p id="login-error" role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
      </div>

      <button
        type="submit"
        disabled={busy || !password}
        className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-br from-indigo-600 to-violet-500 text-sm font-medium text-white shadow-sm transition hover:brightness-110 disabled:opacity-50"
      >
        {busy && <Loader2 className="size-4 animate-spin" />} Sign in
      </button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </main>
  );
}
