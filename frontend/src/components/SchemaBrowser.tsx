import { useQuery } from "@tanstack/react-query";
import { GitBranch, Table2 } from "lucide-react";

import { api } from "../api/client";
import { Badge, Card } from "./ui";

export function SchemaBrowser() {
  const schema = useQuery({ queryKey: ["schema"], queryFn: api.schema });

  return (
    <Card className="space-y-5">
      <div>
        <p className="text-xs uppercase tracking-[0.24em] text-ink-500 dark:text-ink-100">
          Catalog
        </p>
        <h2 className="font-display text-2xl font-bold">Schema browser</h2>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {schema.data?.tables.map((table) => (
          <div className="rounded-3xl border border-ink-100 bg-white/55 p-4 dark:border-white/10 dark:bg-white/5" key={table.id}>
            <div className="mb-3 flex items-start gap-3">
              <Table2 className="mt-1 h-4 w-4 text-harbor-500" />
              <div className="min-w-0">
                <h3 className="truncate font-semibold">{table.canonical_name}</h3>
                <p className="text-sm text-ink-500 dark:text-ink-100">
                  {table.kind} · {table.row_count ?? "unknown"} rows · source table {table.original_name}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {table.columns.map((column) => (
                <Badge key={column.normalized_name}>
                  {column.normalized_name}:{column.data_type}
                </Badge>
              ))}
            </div>
          </div>
        ))}
      </div>

      {schema.data?.relationships.length ? (
        <div>
          <div className="mb-3 flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-harbor-500" />
            <h3 className="font-semibold">Discovered relationships</h3>
          </div>
          <div className="space-y-2">
            {schema.data.relationships.map((rel, index) => (
              <div className="rounded-2xl bg-ink-50 p-3 text-sm dark:bg-white/5" key={index}>
                {rel.left_table}.{rel.left_column} → {rel.right_table}.{rel.right_column}
                <span className="ml-2 text-ink-500 dark:text-ink-100">
                  ({Math.round(rel.confidence * 100)}%, {rel.evidence})
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </Card>
  );
}
