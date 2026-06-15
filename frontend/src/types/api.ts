export type DataSourceType = "sqlite" | "excel" | "csv";
export type UserRole = "admin" | "standard";

export interface AuthUser {
  id: string;
  username: string;
  display_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_login_at?: string | null;
}

export interface UserCreatePayload {
  username: string;
  display_name?: string | null;
  password: string;
  role: UserRole;
  is_active: boolean;
}

export interface UserUpdatePayload {
  display_name?: string | null;
  role?: UserRole;
  is_active?: boolean;
}

export interface StatusEvent {
  step: string;
  status: "pending" | "running" | "completed" | "warning" | "error";
  message: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

export interface SettingsOut {
  app_name: string;
  environment: string;
  llm_base_url: string;
  openai_api_key_configured: boolean;
  model_name: string;
  model_temperature: number;
  model_max_tokens: number;
  model_timeout_seconds: number;
  sql_result_row_limit: number;
  python_timeout_seconds: number;
  qwen_command: string;
  qwen_model?: string | null;
  qwen_timeout_seconds: number;
  qwen_auth_type?: string | null;
  qwen_approval_mode: string;
  qwen_use_sandbox: boolean;
}

export interface DataSource {
  id: string;
  name: string;
  source_type: DataSourceType;
  path: string;
  status: string;
  checksum: string | null;
  last_scanned_at: string | null;
  error: string | null;
  profile: Record<string, unknown>;
}

export interface ContractDocument {
  id: string;
  name: string;
  filename: string;
  path: string;
  extracted_text_path?: string | null;
  content_type?: string | null;
  size_bytes: number;
  created_at: string;
}

export interface ContractWorkspace {
  database?: DataSource | null;
  documents: ContractDocument[];
}

export interface ColumnMetadata {
  original_name: string;
  normalized_name: string;
  data_type: string;
  nullable: boolean | null;
  null_count: number | null;
  sample_values: unknown[];
  ordinal: number;
}

export interface TableMetadata {
  id: string;
  data_source_id: string;
  database_name: string | null;
  original_name: string;
  canonical_name: string;
  kind: string;
  row_count: number | null;
  sample_rows: Record<string, unknown>[];
  columns: ColumnMetadata[];
}

export interface RelationshipMetadata {
  left_table: string;
  left_column: string;
  right_table: string;
  right_column: string;
  confidence: number;
  evidence: string;
}

export interface SchemaOut {
  data_sources: DataSource[];
  tables: TableMetadata[];
  relationships: RelationshipMetadata[];
}

export interface PreviewTableOption {
  canonical_name: string;
  original_name: string;
  row_count: number | null;
}

export interface TablePreview {
  data_source_id: string;
  table: string;
  original_name: string;
  page: number;
  page_size: number;
  total_rows: number | null;
  columns: string[];
  rows: Record<string, unknown>[];
  tables: PreviewTableOption[];
}

export interface TableArtifact {
  type: "table";
  title: string;
  columns: string[];
  rows: Record<string, unknown>[];
  truncated: boolean;
}

export interface ChartArtifact {
  type: "chart";
  title: string;
  spec: Record<string, unknown>;
}

export type Artifact = TableArtifact | ChartArtifact;

export interface SourceReference {
  data_source_id?: string | null;
  data_source_name?: string | null;
  table?: string | null;
  columns: string[];
}

export interface ChatResponse {
  conversation_id: string;
  message_id?: string | null;
  answer: string;
  reasoning_summary: string;
  sql_query?: string | null;
  python_code?: string | null;
  qwen_output?: string | null;
  qwen_workspace?: string | null;
  artifacts: Artifact[];
  sources: SourceReference[];
  caveats: string[];
  confidence: "low" | "medium" | "high";
  status_events: StatusEvent[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | string;
  content: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
}
