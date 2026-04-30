import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Loader2, TableProperties, X } from "lucide-react";

import { api } from "../api/client";
import type { DataSource, TablePreview } from "../types/api";
import { Button } from "./ui";

const PAGE_SIZE = 50;

export function SourcePreviewModal({
  source,
  onClose
}: {
  source: DataSource | null;
  onClose: () => void;
}) {
  const [table, setTable] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    setTable(null);
    setPage(1);
  }, [source?.id]);

  const preview = useQuery({
    queryKey: ["datasource-preview", source?.id, table, page],
    queryFn: () =>
      api.datasourcePreview({
        id: source?.id ?? "",
        table,
        page,
        page_size: PAGE_SIZE
      }),
    enabled: Boolean(source)
  });

  if (!source) return null;

  const data = preview.data;
  const selectedTable = table ?? data?.table ?? "";
  const totalRows = data?.total_rows ?? null;
  const pageCount = totalRows ? Math.max(1, Math.ceil(totalRows / PAGE_SIZE)) : null;
  const canGoNext = pageCount ? page < pageCount : (data?.rows.length ?? 0) === PAGE_SIZE;
  const visibleRange = rangeLabel(data, page);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-950/45 p-4 backdrop-blur-sm">
      <div className="flex max-h-[88vh] w-full max-w-6xl flex-col overflow-hidden rounded-[2rem] border border-white/70 bg-white shadow-2xl dark:border-white/10 dark:bg-ink-900">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-ink-100 p-5 dark:border-white/10">
          <div>
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.24em] text-harbor-700 dark:text-harbor-300">
              <TableProperties className="h-4 w-4" />
              Table preview
            </div>
            <h2 className="mt-2 font-display text-2xl font-bold">{source.name}</h2>
            <p className="mt-1 text-sm text-ink-500 dark:text-ink-100">
              Showing {PAGE_SIZE} rows per page so large files stay responsive.
            </p>
          </div>
          <Button variant="ghost" onClick={onClose}>
            <X className="mr-2 h-4 w-4" />
            Close
          </Button>
        </div>

        <div className="space-y-4 overflow-auto p-5">
          {preview.error ? (
            <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              {preview.error.message}
            </div>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <label className="text-sm font-semibold text-ink-600 dark:text-ink-100">
                Table
              </label>
              <select
                className="rounded-2xl border border-ink-100 bg-white/80 px-4 py-2 text-sm dark:border-white/10 dark:bg-white/5"
                disabled={preview.isLoading || !data?.tables.length}
                value={selectedTable}
                onChange={(event) => {
                  setTable(event.target.value);
                  setPage(1);
                }}
              >
                {data?.tables.map((option) => (
                  <option key={option.canonical_name} value={option.canonical_name}>
                    {option.original_name}{" "}
                    {option.row_count === null ? "" : `(${option.row_count.toLocaleString()} rows)`}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-2 text-sm text-ink-500 dark:text-ink-100">
              <span>{visibleRange}</span>
              <Button
                className="px-3"
                disabled={page <= 1 || preview.isFetching}
                type="button"
                variant="ghost"
                onClick={() => setPage((current) => Math.max(1, current - 1))}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="min-w-20 text-center">
                Page {page}
                {pageCount ? ` / ${pageCount}` : ""}
              </span>
              <Button
                className="px-3"
                disabled={!canGoNext || preview.isFetching}
                type="button"
                variant="ghost"
                onClick={() => setPage((current) => current + 1)}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {preview.isLoading ? (
            <div className="flex items-center gap-3 rounded-3xl border border-ink-100 bg-white/60 p-6 text-ink-500 dark:border-white/10 dark:bg-white/5 dark:text-ink-100">
              <Loader2 className="h-5 w-5 animate-spin" />
              Loading preview…
            </div>
          ) : data ? (
            <PreviewTable preview={data} />
          ) : null}
        </div>
      </div>
    </div>
  );
}

function PreviewTable({ preview }: { preview: TablePreview }) {
  return (
    <div className="overflow-hidden rounded-3xl border border-ink-100 bg-white/70 dark:border-white/10 dark:bg-white/5">
      <div className="overflow-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="sticky top-0 bg-ink-50 text-xs uppercase tracking-wide text-ink-500 dark:bg-ink-900 dark:text-ink-100">
            <tr>
              {preview.columns.map((column) => (
                <th className="whitespace-nowrap px-4 py-3 font-semibold" key={column}>
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.rows.length ? (
              preview.rows.map((row, rowIndex) => (
                <tr className="border-t border-ink-100 dark:border-white/10" key={rowIndex}>
                  {preview.columns.map((column) => (
                    <td className="whitespace-nowrap px-4 py-3" key={column}>
                      {formatCell(row[column])}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-4 py-6 text-center text-ink-500" colSpan={preview.columns.length || 1}>
                  No rows on this page.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function rangeLabel(preview: TablePreview | undefined, page: number) {
  if (!preview) return "No preview loaded";
  if (!preview.rows.length) return "No rows";
  const start = (page - 1) * PAGE_SIZE + 1;
  const end = start + preview.rows.length - 1;
  const total = preview.total_rows === null ? "" : ` of ${preview.total_rows.toLocaleString()}`;
  return `Rows ${start.toLocaleString()}-${end.toLocaleString()}${total}`;
}

function formatCell(value: unknown) {
  if (value === null || value === undefined) return <span className="text-ink-400">null</span>;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
