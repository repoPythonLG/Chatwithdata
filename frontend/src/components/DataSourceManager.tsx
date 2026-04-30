import { ChangeEvent, FormEvent, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, FileSpreadsheet, FileText, FolderOpen, RefreshCw, Trash2 } from "lucide-react";

import { api } from "../api/client";
import type { DataSourceType } from "../types/api";
import { Badge, Button, Card, Input } from "./ui";

export function DataSourceManager() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const datasources = useQuery({ queryKey: ["datasources"], queryFn: api.datasources });
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [sourceType, setSourceType] = useState<DataSourceType>("sqlite");

  const create = useMutation({
    mutationFn: api.createDatasource,
    onSuccess: () => {
      setName("");
      setPath("");
      queryClient.invalidateQueries({ queryKey: ["datasources"] });
      queryClient.invalidateQueries({ queryKey: ["schema"] });
    }
  });
  const upload = useMutation({
    mutationFn: api.uploadDatasource,
    onSuccess: () => {
      setName("");
      setPath("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      queryClient.invalidateQueries({ queryKey: ["datasources"] });
      queryClient.invalidateQueries({ queryKey: ["schema"] });
    }
  });
  const remove = useMutation({
    mutationFn: api.deleteDatasource,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datasources"] });
      queryClient.invalidateQueries({ queryKey: ["schema"] });
    }
  });
  const rescan = useMutation({
    mutationFn: api.rescanDatasources,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datasources"] });
      queryClient.invalidateQueries({ queryKey: ["schema"] });
    }
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate({ name, path, source_type: sourceType });
  }

  function browseForFile() {
    fileInputRef.current?.click();
  }

  function uploadSelectedFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    upload.mutate({ file, name: name || undefined });
  }

  return (
    <Card className="space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-ink-500 dark:text-ink-100">
            Data
          </p>
          <h2 className="font-display text-2xl font-bold">Data sources</h2>
          <p className="mt-1 text-sm text-ink-500 dark:text-ink-100">
            Register local SQLite databases, Excel workbooks, and CSV files without changing application code.
          </p>
        </div>
        <Button variant="ghost" onClick={() => rescan.mutate()} disabled={rescan.isPending}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Rescan
        </Button>
      </div>

      <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
        <Input
          placeholder="Friendly name, optional when browsing"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <div className="flex gap-2">
          <input
            ref={fileInputRef}
            className="hidden"
            type="file"
            accept=".db,.sqlite,.sqlite3,.xls,.xlsx,.xlsm,.csv,.tsv"
            onChange={uploadSelectedFile}
          />
          <Button
            className="min-w-36"
            type="button"
            onClick={browseForFile}
            disabled={upload.isPending}
          >
            <FolderOpen className="mr-2 h-4 w-4" />
            Browse file
          </Button>
        </div>
      </div>

      <form className="grid gap-3 lg:grid-cols-[140px_1.4fr_auto]" onSubmit={submit}>
        <select
          className="rounded-2xl border border-ink-100 bg-white/80 px-4 py-2 text-sm dark:border-white/10 dark:bg-white/5"
          value={sourceType}
          onChange={(event) => setSourceType(event.target.value as DataSourceType)}
        >
          <option value="sqlite">SQLite</option>
          <option value="excel">Excel</option>
          <option value="csv">CSV</option>
        </select>
        <Input
          placeholder="/absolute/path/to/data.sqlite, workbook.xlsx, or data.csv"
          value={path}
          onChange={(event) => setPath(event.target.value)}
        />
        <Button disabled={!name || !path || create.isPending}>Add source</Button>
      </form>

      {create.error ? <p className="text-sm text-red-600">{create.error.message}</p> : null}
      {upload.error ? <p className="text-sm text-red-600">{upload.error.message}</p> : null}
      {upload.isPending ? (
        <p className="text-sm text-ink-500 dark:text-ink-100">
          Uploading and scanning the selected file…
        </p>
      ) : null}

      <div className="grid gap-3">
        {datasources.data?.map((source) => {
          const Icon =
            source.source_type === "excel"
              ? FileSpreadsheet
              : source.source_type === "csv"
                ? FileText
                : Database;
          return (
            <div
              className="flex flex-col gap-3 rounded-3xl border border-ink-100 bg-white/55 p-4 dark:border-white/10 dark:bg-white/5 lg:flex-row lg:items-center"
              key={source.id}
            >
              <Icon className="h-5 w-5 text-harbor-500" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{source.name}</span>
                  <Badge tone={source.status === "active" ? "good" : source.status === "error" ? "bad" : "warn"}>
                    {source.status}
                  </Badge>
                  <Badge>{source.source_type}</Badge>
                </div>
                <p className="truncate text-sm text-ink-500 dark:text-ink-100">{source.path}</p>
                {source.error ? <p className="mt-1 text-sm text-red-600">{source.error}</p> : null}
              </div>
              <Button variant="ghost" onClick={() => remove.mutate(source.id)}>
                <Trash2 className="mr-2 h-4 w-4" />
                Remove
              </Button>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
