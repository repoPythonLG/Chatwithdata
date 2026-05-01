import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, Plus, Trash2 } from "lucide-react";

import { api } from "../api/client";
import type { ChatResponse, Conversation } from "../types/api";
import { Button, Card } from "./ui";

export interface UiMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: ChatResponse;
}

export function ConversationHistoryPanel({
  activeConversationId,
  onNew,
  onLoad
}: {
  activeConversationId: string | null;
  onNew: () => void;
  onLoad: (conversation: Conversation, messages: UiMessage[]) => void;
}) {
  const queryClient = useQueryClient();
  const conversations = useQuery({ queryKey: ["conversations"], queryFn: api.conversations });
  const removeConversation = useMutation({
    mutationFn: api.deleteConversation,
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      if (id === activeConversationId) onNew();
    }
  });
  const clearConversations = useMutation({
    mutationFn: api.clearConversations,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      onNew();
    }
  });

  async function loadConversation(id: string) {
    const conversation = await api.conversation(id);
    const messages = conversation.messages.map((message) => ({
      id: message.id,
      role: message.role === "assistant" ? "assistant" : "user",
      content: message.content,
      response: message.role === "assistant" ? (message.payload as unknown as ChatResponse) : undefined
    })) satisfies UiMessage[];
    onLoad(conversation, messages);
  }

  return (
    <Card className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Conversations</h2>
        <div className="flex gap-2">
          <Button
            variant="primary"
            className="h-10 w-10 rounded-2xl p-0 shadow-harbor-500/15"
            onClick={onNew}
            title="New conversation"
            aria-label="New conversation"
          >
            <Plus className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            className="h-10 w-10 rounded-2xl p-0 text-ink-500 hover:border-red-100 hover:bg-red-50 hover:text-red-600 dark:text-ink-100 dark:hover:border-red-500/20 dark:hover:bg-red-500/10 dark:hover:text-red-200"
            onClick={() => {
              if (window.confirm("Clear all conversation history?")) {
                clearConversations.mutate();
              }
            }}
            disabled={!conversations.data?.length || clearConversations.isPending}
            title="Clear all conversations"
            aria-label="Clear all conversations"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <div className="max-h-80 space-y-2 overflow-auto pr-1">
        {conversations.data?.map((conversation) => (
          <div
            className={[
              "flex w-full items-start gap-2 rounded-2xl p-2 text-left text-sm transition",
              conversation.id === activeConversationId
                ? "bg-harbor-500 text-white"
                : "bg-white/55 text-ink-700 hover:bg-white dark:bg-white/5 dark:text-ink-50 dark:hover:bg-white/10"
            ].join(" ")}
            key={conversation.id}
          >
            <button
              className="flex min-w-0 flex-1 items-start gap-3 p-1 text-left"
              onClick={() => loadConversation(conversation.id)}
              type="button"
            >
              <MessageSquare className="mt-0.5 h-4 w-4 shrink-0" />
              <span className="line-clamp-2">{conversation.title}</span>
            </button>
            <button
              className={[
                "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl transition",
                conversation.id === activeConversationId
                  ? "bg-white/15 text-white hover:bg-white/25"
                  : "text-ink-500 hover:bg-red-50 hover:text-red-600 dark:text-ink-100 dark:hover:bg-red-500/10 dark:hover:text-red-200"
              ].join(" ")}
              disabled={removeConversation.isPending}
              onClick={() => removeConversation.mutate(conversation.id)}
              title={`Remove ${conversation.title}`}
              type="button"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </Card>
  );
}
