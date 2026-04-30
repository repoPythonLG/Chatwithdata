import { useQuery } from "@tanstack/react-query";
import { DatabaseZap } from "lucide-react";

import { api } from "../api/client";
import { Badge, Card } from "./ui";

export function SystemStatusPanel() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 30000 });
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const datasources = useQuery({ queryKey: ["datasources"], queryFn: api.datasources });
  const active = datasources.data?.filter((source) => source.status === "active").length ?? 0;

  return (
    <Card className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-ink-500 dark:text-ink-100">
            System
          </p>
          <h2 className="font-display text-lg font-bold">Runtime status</h2>
        </div>
        <Badge tone={health.data?.status === "ok" ? "good" : "warn"}>
          {(health.data?.status as string) ?? "checking"}
        </Badge>
      </div>
      <div className="grid gap-3 text-sm">
        <div className="flex items-center gap-3">
          <DatabaseZap className="h-4 w-4 text-harbor-500" />
          <span>{active} active data source{active === 1 ? "" : "s"}</span>
        </div>
      </div>
    </Card>
  );
}
