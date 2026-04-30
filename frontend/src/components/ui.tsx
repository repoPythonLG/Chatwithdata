import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  TextareaHTMLAttributes
} from "react";

import { cn } from "../lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <section
      className={cn(
        "rounded-3xl border border-white/60 bg-white/78 p-5 shadow-soft backdrop-blur-xl dark:border-white/10 dark:bg-ink-900/72",
        className
      )}
      {...props}
    />
  );
}

export function Button({
  className,
  variant = "primary",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" }) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-2xl px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" &&
          "bg-harbor-500 text-white shadow-lg shadow-harbor-500/20 hover:bg-harbor-700",
        variant === "ghost" &&
          "border border-ink-100 bg-white/60 text-ink-700 hover:bg-white dark:border-white/10 dark:bg-white/5 dark:text-ink-50 dark:hover:bg-white/10",
        variant === "danger" &&
          "bg-red-600 text-white shadow-lg shadow-red-600/20 hover:bg-red-700",
        className
      )}
      {...props}
    />
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "w-full rounded-2xl border border-ink-100 bg-white/80 px-4 py-2 text-sm outline-none ring-harbor-400 transition placeholder:text-ink-500 focus:ring-2 dark:border-white/10 dark:bg-white/5 dark:text-ink-50",
        className
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "w-full resize-none rounded-3xl border border-ink-100 bg-white/80 px-4 py-3 text-sm outline-none ring-harbor-400 transition placeholder:text-ink-500 focus:ring-2 dark:border-white/10 dark:bg-white/5 dark:text-ink-50",
        className
      )}
      {...props}
    />
  );
}

export function Badge({
  children,
  tone = "neutral"
}: {
  children: ReactNode;
  tone?: "neutral" | "good" | "warn" | "bad";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold",
        tone === "neutral" && "bg-ink-100 text-ink-700 dark:bg-white/10 dark:text-ink-50",
        tone === "good" && "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200",
        tone === "warn" && "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200",
        tone === "bad" && "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-200"
      )}
    >
      {children}
    </span>
  );
}
