import { Code2, Database, MessageSquareText, ShieldAlert } from "lucide-react";

import type { ChatResponse } from "../types/api";
import { ResultViewer } from "./ResultViewer";
import { Badge, Card } from "./ui";

export function AnswerRenderer({ response }: { response: ChatResponse }) {
  return (
    <div className="space-y-4">
      <Card className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <MessageSquareText className="h-4 w-4 text-harbor-500" />
          <Badge tone={response.confidence === "high" ? "good" : response.confidence === "low" ? "warn" : "neutral"}>
            {response.confidence} confidence
          </Badge>
        </div>
        <p className="whitespace-pre-wrap leading-7 text-ink-900 dark:text-ink-50">{response.answer}</p>
        {response.reasoning_summary ? (
          <p className="rounded-2xl bg-ink-50 p-3 text-sm text-ink-700 dark:bg-white/5 dark:text-ink-100">
            {response.reasoning_summary}
          </p>
        ) : null}
      </Card>

      <ResultViewer artifacts={response.artifacts} />

      {(response.sql_query || response.python_code) && (
        <Card className="space-y-4">
          <div className="flex items-center gap-2">
            <Code2 className="h-4 w-4 text-harbor-500" />
            <h3 className="font-semibold">Executed logic</h3>
          </div>
          {response.sql_query ? <CodeBlock title="SQL" code={response.sql_query} /> : null}
          {response.python_code ? <CodeBlock title="Python" code={response.python_code} /> : null}
        </Card>
      )}

      {response.sources.length ? (
        <Card>
          <div className="mb-3 flex items-center gap-2">
            <Database className="h-4 w-4 text-harbor-500" />
            <h3 className="font-semibold">Sources</h3>
          </div>
          <div className="flex flex-wrap gap-2">
            {response.sources.map((source, index) => (
              <Badge key={`${source.table}-${index}`}>
                {source.table}
                {source.columns.length ? ` · ${source.columns.join(", ")}` : ""}
              </Badge>
            ))}
          </div>
        </Card>
      ) : null}

      {response.caveats.length ? (
        <Card className="border-amber-200 bg-amber-50/80 dark:border-amber-500/20 dark:bg-amber-500/10">
          <div className="mb-2 flex items-center gap-2 font-semibold text-amber-900 dark:text-amber-100">
            <ShieldAlert className="h-4 w-4" />
            Caveats
          </div>
          <ul className="space-y-2 text-sm text-amber-900 dark:text-amber-100">
            {response.caveats.map((caveat, index) => (
              <li key={index}>{caveat}</li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}

function CodeBlock({ title, code }: { title: string; code: string }) {
  return (
    <div>
      <div className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-ink-500 dark:text-ink-100">
        {title}
      </div>
      <pre className="max-h-80 overflow-auto rounded-2xl bg-ink-900 p-4 text-xs leading-6 text-ink-50">
        <code>{code}</code>
      </pre>
    </div>
  );
}
