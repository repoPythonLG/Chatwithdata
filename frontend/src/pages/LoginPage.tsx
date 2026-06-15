import { FormEvent, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { LockKeyhole } from "lucide-react";

import { api } from "../api/client";
import { Button, Card, Input } from "../components/ui";

const SABIC_LOGO_URL = "/brand/sabic-logo.svg";

export function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");

  const login = useMutation({
    mutationFn: api.login,
    onSuccess: onLogin
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    login.mutate({ username: username.trim(), password });
  }

  return (
    <div className="grid min-h-screen place-items-center p-5 text-ink-900 dark:text-ink-50">
      <div className="w-full max-w-5xl">
        <div className="grid overflow-hidden rounded-[2.25rem] border border-white/60 bg-white/72 shadow-soft backdrop-blur-xl dark:border-white/10 dark:bg-ink-900/70 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="relative min-h-[420px] overflow-hidden bg-harbor-500 p-8 text-white">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(255,205,0,0.32),transparent_18rem),linear-gradient(135deg,#041e42,#009fdf)]" />
            <div className="relative z-10 flex h-full flex-col justify-between">
              <div>
                <div className="grid h-16 w-44 place-items-center rounded-3xl bg-white px-4 shadow-soft">
                  <img className="h-11 w-auto" src={SABIC_LOGO_URL} alt="SABIC logo" />
                </div>
                <p className="mt-10 text-xs uppercase tracking-[0.3em] text-white/70">
                  Secure workspace
                </p>
                <h1 className="mt-3 font-display text-4xl font-bold tracking-tight">
                  Chat with Contracts
                </h1>
              </div>
            </div>
          </div>

          <Card className="rounded-none border-0 bg-transparent p-8 shadow-none">
            <div className="mb-8">
              <div className="mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-harbor-50 text-harbor-700 dark:bg-harbor-500/15 dark:text-harbor-300">
                <LockKeyhole className="h-5 w-5" />
              </div>
              <p className="text-xs uppercase tracking-[0.24em] text-ink-500 dark:text-ink-100">
                Sign in
              </p>
              <h2 className="mt-2 font-display text-3xl font-bold">Welcome back</h2>
              <p className="mt-2 text-sm text-ink-500 dark:text-ink-100">
                Use your local application account to continue.
              </p>
            </div>

            <form className="grid gap-4" onSubmit={submit}>
              <label className="grid gap-2 text-sm font-semibold">
                Username
                <Input
                  autoComplete="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                />
              </label>
              <label className="grid gap-2 text-sm font-semibold">
                Password
                <Input
                  autoComplete="current-password"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </label>

              {login.error ? (
                <p className="rounded-2xl bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-200">
                  {login.error.message}
                </p>
              ) : null}

              <Button
                className="mt-2 py-3"
                disabled={login.isPending || !username.trim() || !password}
              >
                {login.isPending ? "Signing in…" : "Sign in"}
              </Button>
            </form>
          </Card>
        </div>
      </div>
    </div>
  );
}
