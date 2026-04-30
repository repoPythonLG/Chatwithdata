import { useQuery } from "@tanstack/react-query";
import { MessageSquare, Plus } from "lucide-react";

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
  const conversations = useQuery({ queryKey: ["conversations"], queryFn: api.conversations });

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
        <Button variant="ghost" onClick={onNew}>
          <Plus className="mr-2 h-4 w-4" />
          New
        </Button>
      </div>
      <div className="max-h-80 space-y-2 overflow-auto pr-1">
        {conversations.data?.map((conversation) => (
          <button
            className={[
              "flex w-full items-start gap-3 rounded-2xl p-3 text-left text-sm transition",
              conversation.id === activeConversationId
                ? "bg-harbor-500 text-white"
                : "bg-white/55 text-ink-700 hover:bg-white dark:bg-white/5 dark:text-ink-50 dark:hover:bg-white/10"
            ].join(" ")}
            key={conversation.id}
            onClick={() => loadConversation(conversation.id)}
          >
            <MessageSquare className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="line-clamp-2">{conversation.title}</span>
          </button>
        ))}
      </div>
    </Card>
  );
}
