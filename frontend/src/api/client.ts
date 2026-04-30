import type {
  ChatResponse,
  Conversation,
  DataSource,
  DataSourceType,
  SchemaOut,
  SettingsOut,
  StatusEvent
} from "../types/api";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail ?? "Request failed");
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<Record<string, unknown>>("/health"),
  settings: () => request<SettingsOut>("/settings"),
  updateSettings: (payload: Partial<SettingsOut>) =>
    request<SettingsOut>("/settings", { method: "POST", body: JSON.stringify(payload) }),
  datasources: () => request<DataSource[]>("/datasources"),
  createDatasource: (payload: { name: string; source_type: DataSourceType; path: string }) =>
    request<DataSource>("/datasources", { method: "POST", body: JSON.stringify(payload) }),
  uploadDatasource: async (payload: { file: File; name?: string }) => {
    const form = new FormData();
    form.append("file", payload.file);
    if (payload.name) form.append("name", payload.name);
    const response = await fetch(`${API_BASE}/datasources/upload`, {
      method: "POST",
      body: form
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail ?? "Upload failed");
    }
    return response.json() as Promise<DataSource>;
  },
  deleteDatasource: async (id: string) => {
    const response = await fetch(`${API_BASE}/datasources/${id}`, { method: "DELETE" });
    if (!response.ok) throw new Error(response.statusText);
  },
  rescanDatasources: () =>
    request<DataSource[]>("/datasources/rescan", { method: "POST", body: JSON.stringify({}) }),
  schema: () => request<SchemaOut>("/schema"),
  conversations: () => request<Conversation[]>("/chat"),
  conversation: (id: string) => request<Conversation>(`/chat/${id}`),
  chat: (payload: { message: string; conversation_id?: string | null; selected_data_sources?: string[] }) =>
    request<ChatResponse>("/chat", { method: "POST", body: JSON.stringify(payload) })
};

export interface StreamHandlers {
  onConversation?: (conversationId: string) => void;
  onStatus?: (event: StatusEvent) => void;
  onToken?: (token: string) => void;
  onFinal?: (response: ChatResponse) => void;
  onError?: (message: string) => void;
}

export async function streamChat(
  payload: { message: string; conversation_id?: string | null; selected_data_sources?: string[] },
  handlers: StreamHandlers
) {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, stream: true })
  });
  if (!response.ok || !response.body) {
    throw new Error(response.statusText || "Streaming request failed");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const raw of events) {
      const parsed = parseSse(raw);
      if (!parsed) continue;
      if (parsed.event === "conversation") {
        handlers.onConversation?.(parsed.data.conversation_id as string);
      }
      if (parsed.event === "status") {
        handlers.onStatus?.(parsed.data as unknown as StatusEvent);
      }
      if (parsed.event === "token") {
        handlers.onToken?.((parsed.data.content as string) ?? "");
      }
      if (parsed.event === "final") {
        handlers.onFinal?.(parsed.data as unknown as ChatResponse);
      }
      if (parsed.event === "error") {
        handlers.onError?.((parsed.data.detail as string) ?? "Stream error");
      }
    }
  }
}

function parseSse(raw: string): { event: string; data: Record<string, unknown> } | null {
  const eventLine = raw.split("\n").find((line) => line.startsWith("event:"));
  const dataLine = raw.split("\n").find((line) => line.startsWith("data:"));
  if (!eventLine || !dataLine) return null;
  return {
    event: eventLine.slice("event:".length).trim(),
    data: JSON.parse(dataLine.slice("data:".length).trim())
  };
}
