import { ChangeEvent, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, FileSpreadsheet } from "lucide-react";

import { api } from "../api/client";
import { Badge, Button, Card } from "./ui";

export function ContractWorkspaceManager() {
  const queryClient = useQueryClient();
  const databaseInputRef = useRef<HTMLInputElement | null>(null);
  const workspace = useQuery({
    queryKey: ["contracts"],
    queryFn: api.contractWorkspace
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["contracts"] });
    queryClient.invalidateQueries({ queryKey: ["datasources"] });
    queryClient.invalidateQueries({ queryKey: ["schema"] });
  };

  const uploadDatabase = useMutation({
    mutationFn: api.uploadContractDatabase,
    onSuccess: () => {
      if (databaseInputRef.current) databaseInputRef.current.value = "";
      refresh();
    }
  });

  function uploadSelectedDatabase(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    uploadDatabase.mutate(file);
  }

  const database = workspace.data?.database ?? null;

  return (
    <Card className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-ink-500 dark:text-ink-100">
            Contracts
          </p>
          <h2 className="font-display text-2xl font-bold">Contract workspace</h2>
          <p className="mt-1 text-sm text-ink-500 dark:text-ink-100">
            Upload one Excel contract register. It is converted to a SQLite database and
            used as the structured source for every chat.
          </p>
        </div>
        <Button
          disabled={uploadDatabase.isPending}
          onClick={() => databaseInputRef.current?.click()}
          type="button"
        >
          <FileSpreadsheet className="mr-2 h-4 w-4" />
          Upload Excel DB
        </Button>
      </div>

      <input
        ref={databaseInputRef}
        className="hidden"
        type="file"
        accept=".xls,.xlsx,.xlsm"
        onChange={uploadSelectedDatabase}
      />

      <div className="rounded-3xl border border-ink-100 bg-white/55 p-4 dark:border-white/10 dark:bg-white/5">
        {database ? (
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
            <Database className="h-5 w-5 text-harbor-500" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">{database.name}</span>
                <Badge tone={database.status === "active" ? "good" : "warn"}>
                  {database.status}
                </Badge>
                <Badge>SQLite</Badge>
              </div>
              <p className="truncate text-sm text-ink-500 dark:text-ink-100">
                {String(database.profile?.original_workbook_name ?? database.path)}
              </p>
              {database.error ? <p className="mt-1 text-sm text-red-600">{database.error}</p> : null}
            </div>
          </div>
        ) : (
          <div className="flex items-start gap-3 text-sm text-ink-500 dark:text-ink-100">
            <Database className="mt-0.5 h-5 w-5 text-harbor-500" />
            <div>
              <p className="font-semibold text-ink-900 dark:text-white">
                No contract database configured.
              </p>
              <p>Upload an Excel workbook before asking contract questions.</p>
            </div>
          </div>
        )}
      </div>

      {uploadDatabase.error ? (
        <p className="text-sm text-red-600">{uploadDatabase.error.message}</p>
      ) : null}
      {uploadDatabase.isPending ? (
        <p className="text-sm text-ink-500 dark:text-ink-100">
          Uploading workbook and converting worksheets into SQLite tables…
        </p>
      ) : null}
    </Card>
  );
}
