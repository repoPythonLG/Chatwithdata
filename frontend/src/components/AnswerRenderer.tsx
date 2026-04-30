import { Code2, Database, MessageSquareText, ShieldAlert } from "lucide-react";

import { useAppStore } from "../store/appStore";
import type { ChatResponse } from "../types/api";
import { ResultViewer } from "./ResultViewer";
import { Badge, Card } from "./ui";

export function AnswerRenderer({ response }: { response: ChatResponse }) {
  const showAdvancedDetails = useAppStore((state) => state.responseMode === "advanced");

  return (
    <div className="space-y-4">
      <Card className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <MessageSquareText className="h-4 w-4 text-harbor-500" />
          <Badge tone={response.confidence === "high" ? "good" : response.confidence === "low" ? "warn" : "neutral"}>
            {response.confidence} confidence
          </Badge>
        </div>
        <FormattedAnswer text={response.answer} />
        {response.reasoning_summary ? (
          <p className="rounded-2xl bg-ink-50 p-3 text-sm leading-6 text-ink-700 dark:bg-white/5 dark:text-ink-100">
            <span className="font-semibold">How this was answered: </span>
            {response.reasoning_summary}
          </p>
        ) : null}
      </Card>

      <ResultViewer artifacts={response.artifacts} />

      {showAdvancedDetails && (response.sql_query || response.python_code) && (
        <Card className="space-y-4">
          <div className="flex items-center gap-2">
            <Code2 className="h-4 w-4 text-harbor-500" />
            <h3 className="font-semibold">Generated logic</h3>
          </div>
          {response.sql_query ? <CodeBlock title="SQL query" code={response.sql_query} /> : null}
          {response.python_code ? <CodeBlock title="Python code" code={response.python_code} /> : null}
        </Card>
      )}

      {showAdvancedDetails && response.sources.length ? (
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

      {showAdvancedDetails && response.caveats.length ? (
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

function FormattedAnswer({ text }: { text: string }) {
  const blocks = toBlocks(text);

  return (
    <div className="space-y-4 leading-7 text-ink-900 dark:text-ink-50">
      {blocks.map((block, index) =>
        block.type === "list" ? (
          <ul className="space-y-2" key={index}>
            {block.items.map((item, itemIndex) => (
              <li className="flex gap-3" key={`${index}-${itemIndex}`}>
                <span className="mt-3 h-1.5 w-1.5 shrink-0 rounded-full bg-harbor-500" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className={index === 0 ? "text-lg font-semibold" : ""} key={index}>
            {block.text}
          </p>
        )
      )}
    </div>
  );
}

type AnswerBlock =
  | { type: "paragraph"; text: string }
  | { type: "list"; items: string[] };

function toBlocks(text: string): AnswerBlock[] {
  const blocks: AnswerBlock[] = [];
  let pendingList: string[] = [];

  function flushList() {
    if (pendingList.length) {
      blocks.push({ type: "list", items: pendingList });
      pendingList = [];
    }
  }

  text.split("\n").forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      flushList();
      return;
    }
    if (line.startsWith("- ")) {
      pendingList.push(line.slice(2));
      return;
    }
    flushList();
    blocks.push({ type: "paragraph", text: line });
  });
  flushList();

  return blocks;
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
