import { useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleDashed,
  TriangleAlert,
  XCircle
} from "lucide-react";

import { useAppStore } from "../store/appStore";
import type { StatusEvent } from "../types/api";
import { Badge } from "./ui";

const toneByStatus = {
  pending: "neutral",
  running: "warn",
  completed: "good",
  warning: "warn",
  error: "bad"
} as const;

export function StatusTimeline({ events }: { events: StatusEvent[] }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const responseMode = useAppStore((state) => state.responseMode);
  if (responseMode === "simple") return null;

  const latestByStep = events.reduce<Record<string, StatusEvent>>((acc, event) => {
    acc[event.step] = event;
    return acc;
  }, {});
  const ordered = [
    "Planning",
    "Inspecting schema",
    "Generating query",
    "Generating code",
    "Validating",
    "Executing",
    "Intelligence Engine",
    "Critiquing answer",
    "Finalizing"
  ].filter((step) => latestByStep[step]);

  if (!ordered.length) return null;
  const currentEvent =
    [...events].reverse().find((event) => event.status === "running") ?? events[events.length - 1];
  const visibleSteps = isExpanded ? ordered : ordered.filter((step) => step === currentEvent?.step);

  return (
    <div className="space-y-3">
      <button
        className="flex w-full items-center justify-between rounded-2xl border border-ink-100 bg-white/60 px-4 py-3 text-left transition hover:bg-white dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10"
        type="button"
        onClick={() => setIsExpanded((value) => !value)}
      >
        <div>
          <p className="text-xs uppercase tracking-[0.22em] text-ink-500 dark:text-ink-100">
            Execution steps
          </p>
          {currentEvent ? (
            <p className="mt-1 text-sm font-semibold text-ink-900 dark:text-ink-50">
              {currentEvent.step}: {currentEvent.message}
            </p>
          ) : null}
        </div>
        <span className="flex items-center gap-2 text-sm font-semibold text-harbor-700 dark:text-harbor-300">
          {isExpanded ? "Collapse" : "Show all"}
          {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </span>
      </button>

      {visibleSteps.map((step) => {
        const event = latestByStep[step];
        const Icon =
          event.status === "completed"
            ? CheckCircle2
            : event.status === "error"
              ? XCircle
              : event.status === "warning"
                ? TriangleAlert
                : CircleDashed;
        return (
          <div key={step} className="flex items-start gap-3 text-sm">
            <Icon className="mt-0.5 h-4 w-4 text-harbor-500" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-ink-900 dark:text-ink-50">{step}</span>
                <Badge tone={toneByStatus[event.status]}>{event.status}</Badge>
              </div>
              <p className="mt-1 text-ink-500 dark:text-ink-100">{event.message}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
