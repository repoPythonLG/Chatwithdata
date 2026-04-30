import { CheckCircle2, CircleDashed, TriangleAlert, XCircle } from "lucide-react";

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
    "Critiquing answer",
    "Finalizing"
  ].filter((step) => latestByStep[step]);

  if (!ordered.length) return null;

  return (
    <div className="space-y-3">
      {ordered.map((step) => {
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
