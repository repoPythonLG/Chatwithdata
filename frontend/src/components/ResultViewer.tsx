import { Suspense, lazy } from "react";

import type { Artifact, ChartArtifact, TableArtifact } from "../types/api";
import { Card } from "./ui";

const Plot = lazy(() => import("react-plotly.js"));

export function ResultViewer({ artifacts }: { artifacts: Artifact[] }) {
  if (!artifacts.length) return null;
  return (
    <div className="space-y-4">
      {artifacts.map((artifact, index) =>
        artifact.type === "table" ? (
          <TableResult artifact={artifact} key={`${artifact.title}-${index}`} />
        ) : (
          <ChartResult artifact={artifact} key={`${artifact.title}-${index}`} />
        )
      )}
    </div>
  );
}

function TableResult({ artifact }: { artifact: TableArtifact }) {
  return (
    <Card className="overflow-hidden p-0">
      <div className="flex items-center justify-between border-b border-ink-100 px-4 py-3 dark:border-white/10">
        <h3 className="font-semibold">{artifact.title}</h3>
        {artifact.truncated ? <span className="text-xs text-brass-700">Preview truncated</span> : null}
      </div>
      <div className="max-h-96 overflow-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="sticky top-0 bg-ink-50 text-xs uppercase tracking-wide text-ink-500 dark:bg-ink-900 dark:text-ink-100">
            <tr>
              {artifact.columns.map((column) => (
                <th className="whitespace-nowrap px-4 py-3 font-semibold" key={column}>
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {artifact.rows.map((row, rowIndex) => (
              <tr className="border-t border-ink-100 dark:border-white/10" key={rowIndex}>
                {artifact.columns.map((column) => (
                  <td className="whitespace-nowrap px-4 py-3 text-ink-700 dark:text-ink-50" key={column}>
                    {formatCell(row[column])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function ChartResult({ artifact }: { artifact: ChartArtifact }) {
  const spec = artifact.spec as { data?: unknown[]; layout?: Record<string, unknown> };
  return (
    <Card>
      <h3 className="mb-3 font-semibold">{artifact.title}</h3>
      <div className="overflow-hidden rounded-2xl bg-white dark:bg-white/5">
        <Suspense fallback={<div className="grid h-[420px] place-items-center text-sm">Loading chart…</div>}>
          <Plot
            data={(spec.data ?? []) as any}
            layout={{ autosize: true, height: 420, paper_bgcolor: "transparent", ...spec.layout } as any}
            useResizeHandler
            className="h-full w-full"
          />
        </Suspense>
      </div>
    </Card>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
