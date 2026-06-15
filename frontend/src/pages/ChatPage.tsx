import { type ChangeEvent, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, Database, Eye, FileText, Loader2, Trash2, Upload } from "lucide-react";

import { api, streamChat } from "../api/client";
import { AnswerRenderer, QwenOutputPanel } from "../components/AnswerRenderer";
import {
  ConversationHistoryPanel,
  type UiMessage
} from "../components/ConversationHistoryPanel";
import { StatusTimeline } from "../components/StatusTimeline";
import { SourcePreviewModal } from "../components/SourcePreviewModal";
import { SystemStatusPanel } from "../components/SystemStatusPanel";
import { Badge, Button, Card, Textarea } from "../components/ui";
import { useAppStore } from "../store/appStore";
import type { ChatResponse, Conversation, DataSource, StatusEvent } from "../types/api";

export function ChatPage() {
  const queryClient = useQueryClient();
  const messagesViewportRef = useRef<HTMLDivElement | null>(null);
  const documentInputRef = useRef<HTMLInputElement | null>(null);
  const shouldFollowOutputRef = useRef(true);
  const contracts = useQuery({ queryKey: ["contracts"], queryFn: api.contractWorkspace });
  const responseMode = useAppStore((state) => state.responseMode);
  const conversationId = useAppStore((state) => state.conversationId);
  const setConversationId = useAppStore((state) => state.setConversationId);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [events, setEvents] = useState<StatusEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [previewSource, setPreviewSource] = useState<DataSource | null>(null);
  const contractDatabase = contracts.data?.database ?? null;
  const contractDocuments = contracts.data?.documents ?? [];

  const refreshContracts = () => {
    queryClient.invalidateQueries({ queryKey: ["contracts"] });
  };

  const uploadDocuments = useMutation({
    mutationFn: api.uploadContractDocuments,
    onSuccess: () => {
      if (documentInputRef.current) documentInputRef.current.value = "";
      refreshContracts();
    }
  });

  const removeDocument = useMutation({
    mutationFn: api.deleteContractDocument,
    onSuccess: refreshContracts
  });

  useEffect(() => {
    if (!shouldFollowOutputRef.current) return;
    const viewport = messagesViewportRef.current;
    if (!viewport) return;

    requestAnimationFrame(() => {
      viewport.scrollTop = viewport.scrollHeight;
    });
  }, [messages, events.length, isStreaming]);

  function handleMessagesScroll() {
    const viewport = messagesViewportRef.current;
    if (!viewport) return;
    shouldFollowOutputRef.current = isNearBottom(viewport);
  }

  function uploadSelectedDocuments(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;
    uploadDocuments.mutate(files);
  }

  async function submit(event?: { preventDefault: () => void }) {
    event?.preventDefault();
    const question = input.trim();
    if (!question || isStreaming) return;

    const userMessage: UiMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: question
    };
    const assistantId = crypto.randomUUID();
    setMessages((current) => [
      ...current,
      userMessage,
      { id: assistantId, role: "assistant", content: "" }
    ]);
    setInput("");
    setEvents([]);
    setIsStreaming(true);
    shouldFollowOutputRef.current = true;

    try {
      await streamChat(
        {
          message: question,
          conversation_id: conversationId,
          selected_data_sources: contractDatabase ? [contractDatabase.id] : undefined,
          engine: "qwen_cli"
        },
        {
          onConversation: setConversationId,
          onStatus: (status) => setEvents((current) => [...current, status]),
          onToken: (token) =>
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? { ...message, content: `${message.content}${token}` }
                  : message
              )
            ),
          onQwenOutput: (content) =>
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? { ...message, qwenOutput: `${message.qwenOutput ?? ""}${content}` }
                  : message
              )
            ),
          onFinal: (response: ChatResponse) => {
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? { ...message, content: response.answer, response }
                  : message
              )
            );
            queryClient.invalidateQueries({ queryKey: ["conversations"] });
          },
          onError: (message) =>
            setMessages((current) =>
              current.map((item) =>
                item.id === assistantId ? { ...item, content: `Stream error: ${message}` } : item
              )
            )
        }
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "Streaming request failed";
      setMessages((current) =>
        current.map((item) =>
          item.id === assistantId ? { ...item, content: `Request failed: ${message}` } : item
        )
      );
    } finally {
      setIsStreaming(false);
    }
  }

  function newConversation() {
    setConversationId(null);
    setMessages([]);
    setEvents([]);
    shouldFollowOutputRef.current = true;
    void api.clearContractDocuments().finally(() => {
      queryClient.invalidateQueries({ queryKey: ["contracts"] });
    });
  }

  function loadConversation(conversation: Conversation, loadedMessages: UiMessage[]) {
    setConversationId(conversation.id);
    setMessages(loadedMessages);
    setEvents([]);
    shouldFollowOutputRef.current = true;
  }

  return (
    <div className="grid h-[calc(100vh-8rem)] min-h-0 gap-5 xl:grid-cols-[320px_1fr]">
      <aside className="min-h-0 space-y-5 overflow-auto pr-1">
        <SystemStatusPanel />
        <ConversationHistoryPanel
          activeConversationId={conversationId}
          onLoad={loadConversation}
          onNew={newConversation}
        />
        <Card className="space-y-3 p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-harbor-500" />
              <h2 className="font-semibold">Contract workspace</h2>
            </div>
            <Button
              className="h-9 px-3 text-xs"
              disabled={uploadDocuments.isPending}
              onClick={() => documentInputRef.current?.click()}
              type="button"
              variant="ghost"
            >
              <Upload className="mr-1.5 h-3.5 w-3.5" />
              Attach
            </Button>
          </div>
          <div className="space-y-2">
            {contractDatabase ? (
              <div
                className="flex w-full items-center gap-2 rounded-2xl border border-harbor-400 bg-harbor-400/10 p-2 text-sm"
                key={contractDatabase.id}
              >
                <div className="min-w-0 flex-1 p-1">
                  <span className="block truncate font-semibold">{contractDatabase.name}</span>
                  <span className="text-xs text-ink-500 dark:text-ink-100">
                    Structured SQLite database
                  </span>
                </div>
                <button
                  className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-ink-100 bg-white/70 text-harbor-700 transition hover:bg-white dark:border-white/10 dark:bg-white/5 dark:text-harbor-300 dark:hover:bg-white/10"
                  onClick={() => setPreviewSource(contractDatabase)}
                  title="Preview contract database"
                  type="button"
                >
                  <Eye className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <p className="rounded-2xl border border-dashed border-ink-100 p-3 text-sm text-ink-500 dark:border-white/10 dark:text-ink-100">
                Upload an Excel contract register in Settings before chatting.
              </p>
            )}
          </div>
          {uploadDocuments.error ? (
            <p className="rounded-2xl bg-red-50 p-3 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-200">
              {uploadDocuments.error.message}
            </p>
          ) : null}
          {contractDocuments.length ? (
            <div className="space-y-2 border-t border-ink-100 pt-3 dark:border-white/10">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-ink-500 dark:text-ink-100">
                Documents
              </p>
              {contractDocuments.map((document) => (
                <div
                  className="flex items-start gap-2 rounded-2xl bg-white/55 p-2 text-xs dark:bg-white/5"
                  key={document.id}
                >
                  <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-harbor-500" />
                  <span className="line-clamp-2 min-w-0 flex-1">{document.filename}</span>
                  <button
                    className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-ink-500 transition hover:bg-white hover:text-red-600 dark:text-ink-100 dark:hover:bg-white/10"
                    disabled={removeDocument.isPending}
                    onClick={() => removeDocument.mutate(document.id)}
                    title={`Remove ${document.filename}`}
                    type="button"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="rounded-2xl border border-dashed border-ink-100 p-3 text-sm text-ink-500 dark:border-white/10 dark:text-ink-100">
              Attach one or more contract documents from this chat window.
            </p>
          )}
          <p className="text-xs text-ink-500 dark:text-ink-100">
            New conversation clears uploaded contract documents.
          </p>
        </Card>
      </aside>

      <main className="flex min-h-0 flex-col rounded-[2rem] border border-white/60 bg-white/58 shadow-soft backdrop-blur-xl dark:border-white/10 dark:bg-ink-900/62">
        <div className="border-b border-ink-100 p-5 dark:border-white/10">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-harbor-700 dark:text-harbor-400">
                Contract intelligence
              </p>
            </div>
            <Badge tone={isStreaming ? "warn" : "good"}>
              {isStreaming ? "Streaming" : "Ready"}
            </Badge>
          </div>
        </div>

        <div
          className="min-h-0 flex-1 space-y-5 overflow-auto p-5"
          onScroll={handleMessagesScroll}
          ref={messagesViewportRef}
        >
          {!messages.length ? (
            <EmptyState onExample={setInput} />
          ) : (
            messages.map((message) => (
              <div
                className={[
                  "animate-rise-in",
                  message.role === "user" ? "ml-auto max-w-3xl" : "mr-auto max-w-5xl"
                ].join(" ")}
                key={message.id}
              >
                {message.role === "user" ? (
                  <div className="rounded-3xl bg-ink-900 px-5 py-4 text-white shadow-soft dark:bg-harbor-700">
                    {message.content}
                  </div>
                ) : message.response ? (
                  <AnswerRenderer response={message.response} />
                ) : (
                  <Card className="space-y-4">
                    {message.content ? (
                      <p className="whitespace-pre-wrap leading-7">{message.content}</p>
                    ) : (
                      <div className="flex items-center gap-3 text-ink-500 dark:text-ink-100">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Waiting for streamed response…
                      </div>
                    )}
                    {responseMode === "advanced" && message.qwenOutput ? (
                      <QwenOutputPanel output={message.qwenOutput} />
                    ) : null}
                  </Card>
                )}
              </div>
            ))
          )}
        </div>

        {events.length ? (
          <div className="border-t border-ink-100 bg-white/40 p-5 dark:border-white/10 dark:bg-white/5">
            <StatusTimeline events={events} />
          </div>
        ) : null}

        <form className="border-t border-ink-100 p-5 dark:border-white/10" onSubmit={submit}>
          <input
            ref={documentInputRef}
            className="hidden"
            type="file"
            multiple
            accept=".pdf,.doc,.docx,.pptx,.html,.htm,.txt,.text,.md,.rtf,.json,.csv,.xls,.xlsx,.xlsm,.png,.jpg,.jpeg,.tif,.tiff,.webp,.bmp"
            onChange={uploadSelectedDocuments}
          />
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <Button
              className="px-3 py-2 text-sm"
              disabled={uploadDocuments.isPending}
              onClick={() => documentInputRef.current?.click()}
              type="button"
              variant="ghost"
            >
              <Upload className="mr-2 h-4 w-4" />
              {uploadDocuments.isPending ? "Uploading documents…" : "Attach contract documents"}
            </Button>
            <span className="text-xs text-ink-500 dark:text-ink-100">
              {contractDocuments.length
                ? `${contractDocuments.length} document${
                    contractDocuments.length === 1 ? "" : "s"
                  } attached for this chat`
                : "Optional: attach PDFs, Word files, spreadsheets, CSVs, or text files"}
            </span>
          </div>
          <div className="flex gap-3">
            <Textarea
              className="min-h-[76px] flex-1"
              placeholder="Ask about contracts, suppliers, dates, obligations, risks, or uploaded documents…"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                  submit(event);
                }
              }}
            />
            <Button className="self-end px-5 py-4" disabled={isStreaming || !input.trim()}>
              <ArrowUp className="h-5 w-5" />
            </Button>
          </div>
        </form>
      </main>
      <SourcePreviewModal source={previewSource} onClose={() => setPreviewSource(null)} />
    </div>
  );
}

function isNearBottom(element: HTMLElement) {
  return element.scrollHeight - element.scrollTop - element.clientHeight < 96;
}

function EmptyState({ onExample }: { onExample: (value: string) => void }) {
  const examples = [
    "Which contracts expire in the next 90 days?",
    "Summarize high-risk suppliers and explain why they are high risk.",
    "Compare contract value by business unit and contract owner.",
    "Use the uploaded contract documents to identify unusual obligations."
  ];

  return (
    <div className="grid min-h-[300px] place-items-center">
      <div className="max-w-3xl text-center">
        <p className="text-xs uppercase tracking-[0.28em] text-brass-700 dark:text-brass-300">
          Start with a contract question
        </p>
        <h2 className="mt-3 font-display text-3xl font-bold tracking-tight">
          Your contract database, one careful analyst.
        </h2>
        <div className="mt-6 grid gap-3 md:grid-cols-2">
          {examples.map((example) => (
            <button
              className="rounded-3xl border border-ink-100 bg-white/70 p-4 text-left text-sm transition hover:-translate-y-0.5 hover:bg-white dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10"
              key={example}
              onClick={() => onExample(example)}
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
