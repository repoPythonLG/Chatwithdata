import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, Database, Loader2 } from "lucide-react";

import { api, streamChat } from "../api/client";
import { AnswerRenderer } from "../components/AnswerRenderer";
import {
  ConversationHistoryPanel,
  type UiMessage
} from "../components/ConversationHistoryPanel";
import { StatusTimeline } from "../components/StatusTimeline";
import { SystemStatusPanel } from "../components/SystemStatusPanel";
import { Badge, Button, Card, Textarea } from "../components/ui";
import { useAppStore } from "../store/appStore";
import type { ChatResponse, Conversation, StatusEvent } from "../types/api";

export function ChatPage() {
  const queryClient = useQueryClient();
  const messagesViewportRef = useRef<HTMLDivElement | null>(null);
  const shouldFollowOutputRef = useRef(true);
  const datasources = useQuery({ queryKey: ["datasources"], queryFn: api.datasources });
  const selectedDataSources = useAppStore((state) => state.selectedDataSources);
  const setSelectedDataSources = useAppStore((state) => state.setSelectedDataSources);
  const toggleDataSource = useAppStore((state) => state.toggleDataSource);
  const conversationId = useAppStore((state) => state.conversationId);
  const setConversationId = useAppStore((state) => state.setConversationId);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [events, setEvents] = useState<StatusEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const activeSources = useMemo(
    () => datasources.data?.filter((source) => source.status === "active") ?? [],
    [datasources.data]
  );
  const activeSourceIds = useMemo(() => new Set(activeSources.map((source) => source.id)), [activeSources]);
  const effectiveSelectedDataSources = useMemo(
    () => selectedDataSources.filter((id) => activeSourceIds.has(id)),
    [activeSourceIds, selectedDataSources]
  );

  useEffect(() => {
    if (!datasources.data) return;
    if (effectiveSelectedDataSources.length === selectedDataSources.length) return;
    setSelectedDataSources(effectiveSelectedDataSources);
  }, [datasources.data, effectiveSelectedDataSources, selectedDataSources, setSelectedDataSources]);

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
          selected_data_sources: effectiveSelectedDataSources.length
            ? effectiveSelectedDataSources
            : undefined
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
          <div className="flex items-center gap-2">
            <Database className="h-4 w-4 text-harbor-500" />
            <h2 className="font-semibold">Active sources</h2>
          </div>
          <div className="space-y-2">
            {activeSources.map((source) => {
              const selected =
                effectiveSelectedDataSources.length === 0 ||
                effectiveSelectedDataSources.includes(source.id);
              return (
                <button
                  className={[
                    "w-full rounded-2xl border p-3 text-left text-sm transition",
                    selected
                      ? "border-harbor-400 bg-harbor-400/10"
                      : "border-ink-100 bg-white/40 opacity-70 dark:border-white/10 dark:bg-white/5"
                  ].join(" ")}
                  key={source.id}
                  onClick={() => toggleDataSource(source.id)}
                >
                  <span className="font-semibold">{source.name}</span>
                  <span className="ml-2 text-xs text-ink-500 dark:text-ink-100">
                    {source.source_type}
                  </span>
                </button>
              );
            })}
          </div>
          <p className="text-xs text-ink-500 dark:text-ink-100">
            No selection means the agent may use all active sources.
          </p>
        </Card>
      </aside>

      <main className="flex min-h-0 flex-col rounded-[2rem] border border-white/60 bg-white/58 shadow-soft backdrop-blur-xl dark:border-white/10 dark:bg-ink-900/62">
        <div className="border-b border-ink-100 p-5 dark:border-white/10">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-harbor-700 dark:text-harbor-400">
                AI data analyst
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
                  <Card>
                    {message.content ? (
                      <p className="whitespace-pre-wrap leading-7">{message.content}</p>
                    ) : (
                      <div className="flex items-center gap-3 text-ink-500 dark:text-ink-100">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Waiting for streamed response…
                      </div>
                    )}
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
          <div className="flex gap-3">
            <Textarea
              className="min-h-[76px] flex-1"
              placeholder="Ask for rankings, trends, joins, quality checks, or a chart…"
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
    </div>
  );
}

function isNearBottom(element: HTMLElement) {
  return element.scrollHeight - element.scrollTop - element.clientHeight < 96;
}

function EmptyState({ onExample }: { onExample: (value: string) => void }) {
  const examples = [
    "Which customers had the highest revenue last quarter?",
    "Find data-quality issues across sheets and explain the impact.",
    "Plot monthly order volume and flag unusual changes.",
    "Join orders to customers and rank regions by average order value."
  ];

  return (
    <div className="grid min-h-[300px] place-items-center">
      <div className="max-w-3xl text-center">
        <p className="text-xs uppercase tracking-[0.28em] text-brass-700 dark:text-brass-300">
          Start with a business question
        </p>
        <h2 className="mt-3 font-display text-3xl font-bold tracking-tight">
          Your local data, one careful analyst.
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
