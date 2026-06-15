import type {
  AuthUser,
  ChatResponse,
  ContractDocument,
  ContractWorkspace,
  Conversation,
  DataSource,
  DataSourceType,
  SchemaOut,
  SettingsOut,
  StatusEvent,
  TablePreview,
  UserCreatePayload,
  UserUpdatePayload
} from "../types/api";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
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
  currentUser: () => request<AuthUser>("/auth/me"),
  login: (payload: { username: string; password: string }) =>
    request<AuthUser>("/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  logout: async () => {
    const response = await fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      credentials: "include"
    });
    if (!response.ok) throw new Error(response.statusText);
  },
  users: () => request<AuthUser[]>("/users"),
  createUser: (payload: UserCreatePayload) =>
    request<AuthUser>("/users", { method: "POST", body: JSON.stringify(payload) }),
  updateUser: (id: string, payload: UserUpdatePayload) =>
    request<AuthUser>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  updateUserPassword: (id: string, password: string) =>
    request<AuthUser>(`/users/${id}/password`, {
      method: "POST",
      body: JSON.stringify({ password })
    }),
  deactivateUser: async (id: string) => {
    const response = await fetch(`${API_BASE}/users/${id}`, {
      method: "DELETE",
      credentials: "include"
    });
    if (!response.ok) throw new Error(response.statusText);
  },
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
      credentials: "include",
      body: form
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail ?? "Upload failed");
    }
    return response.json() as Promise<DataSource>;
  },
  deleteDatasource: async (id: string) => {
    const response = await fetch(`${API_BASE}/datasources/${id}`, {
      method: "DELETE",
      credentials: "include"
    });
    if (!response.ok) throw new Error(response.statusText);
  },
  datasourcePreview: (payload: {
    id: string;
    table?: string | null;
    page?: number;
    page_size?: number;
  }) => {
    const params = new URLSearchParams();
    if (payload.table) params.set("table", payload.table);
    if (payload.page) params.set("page", String(payload.page));
    if (payload.page_size) params.set("page_size", String(payload.page_size));
    const query = params.toString();
    return request<TablePreview>(`/datasources/${payload.id}/preview${query ? `?${query}` : ""}`);
  },
  rescanDatasources: () =>
    request<DataSource[]>("/datasources/rescan", { method: "POST", body: JSON.stringify({}) }),
  contractWorkspace: () => request<ContractWorkspace>("/contracts"),
  uploadContractDatabase: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const response = await fetch(`${API_BASE}/contracts/database/upload`, {
      method: "POST",
      credentials: "include",
      body: form
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail ?? "Contract database upload failed");
    }
    return response.json() as Promise<ContractWorkspace>;
  },
  uploadContractDocuments: async (files: File[]) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    const response = await fetch(`${API_BASE}/contracts/documents/upload`, {
      method: "POST",
      credentials: "include",
      body: form
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail ?? "Contract document upload failed");
    }
    return response.json() as Promise<ContractDocument[]>;
  },
  deleteContractDocument: async (id: string) => {
    const response = await fetch(`${API_BASE}/contracts/documents/${id}`, {
      method: "DELETE",
      credentials: "include"
    });
    if (!response.ok) throw new Error(response.statusText);
  },
  clearContractDocuments: async () => {
    const response = await fetch(`${API_BASE}/contracts/documents`, {
      method: "DELETE",
      credentials: "include"
    });
    if (!response.ok) throw new Error(response.statusText);
  },
  schema: () => request<SchemaOut>("/schema"),
  conversations: () => request<Conversation[]>("/chat"),
  conversation: (id: string) => request<Conversation>(`/chat/${id}`),
  deleteConversation: async (id: string) => {
    const response = await fetch(`${API_BASE}/chat/${id}`, {
      method: "DELETE",
      credentials: "include"
    });
    if (!response.ok) throw new Error(response.statusText);
  },
  clearConversations: async () => {
    const response = await fetch(`${API_BASE}/chat`, { method: "DELETE", credentials: "include" });
    if (!response.ok) throw new Error(response.statusText);
  },
  chat: (payload: {
    message: string;
    conversation_id?: string | null;
    selected_data_sources?: string[];
    engine?: "standard" | "qwen_cli";
  }) =>
    request<ChatResponse>("/chat", { method: "POST", body: JSON.stringify(payload) })
};

export interface StreamHandlers {
  onConversation?: (conversationId: string) => void;
  onStatus?: (event: StatusEvent) => void;
  onToken?: (token: string) => void;
  onQwenOutput?: (content: string) => void;
  onFinal?: (response: ChatResponse) => void;
  onError?: (message: string) => void;
}

export async function streamChat(
  payload: {
    message: string;
    conversation_id?: string | null;
    selected_data_sources?: string[];
    engine?: "standard" | "qwen_cli";
  },
  handlers: StreamHandlers
) {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    credentials: "include",
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
      if (parsed.event === "qwen_output") {
        handlers.onQwenOutput?.((parsed.data.content as string) ?? "");
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
  const dataLines = raw
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice("data:".length).trimStart());
  if (!eventLine || !dataLines.length) return null;
  return {
    event: eventLine.slice("event:".length).trim(),
    data: JSON.parse(dataLines.join("\n"))
  };
}
