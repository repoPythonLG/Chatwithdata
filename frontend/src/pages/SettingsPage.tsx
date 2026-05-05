import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import { DataSourceManager } from "../components/DataSourceManager";
import { SchemaBrowser } from "../components/SchemaBrowser";
import { SystemStatusPanel } from "../components/SystemStatusPanel";
import { Button, Card, Input } from "../components/ui";
import { useAppStore } from "../store/appStore";

export function SettingsPage() {
  const queryClient = useQueryClient();
  const responseMode = useAppStore((state) => state.responseMode);
  const setResponseMode = useAppStore((state) => state.setResponseMode);
  const analysisEngine = useAppStore((state) => state.analysisEngine);
  const setAnalysisEngine = useAppStore((state) => state.setAnalysisEngine);
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [llmBaseUrl, setLlmBaseUrl] = useState("");
  const [modelName, setModelName] = useState("qwen3-coder-next");
  const [apiKey, setApiKey] = useState("");
  const [temperature, setTemperature] = useState("0.1");
  const [maxTokens, setMaxTokens] = useState("4096");
  const [qwenCommand, setQwenCommand] = useState("qwen");
  const [qwenModel, setQwenModel] = useState("");
  const [qwenTimeout, setQwenTimeout] = useState("300");
  const [qwenAuthType, setQwenAuthType] = useState("openai");
  const [qwenApprovalMode, setQwenApprovalMode] = useState("yolo");
  const [qwenUseSandbox, setQwenUseSandbox] = useState(true);

  useEffect(() => {
    if (!settings.data) return;
    setLlmBaseUrl(settings.data.llm_base_url);
    setModelName(settings.data.model_name);
    setTemperature(String(settings.data.model_temperature));
    setMaxTokens(String(settings.data.model_max_tokens));
    setQwenCommand(settings.data.qwen_command || "qwen");
    setQwenModel(settings.data.qwen_model ?? "");
    setQwenTimeout(String(settings.data.qwen_timeout_seconds));
    setQwenAuthType(settings.data.qwen_auth_type || "openai");
    setQwenApprovalMode(settings.data.qwen_approval_mode || "yolo");
    setQwenUseSandbox(settings.data.qwen_use_sandbox);
  }, [settings.data]);

  const update = useMutation({
    mutationFn: api.updateSettings,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] })
  });

  function settingsPayload() {
    return {
      llm_base_url: llmBaseUrl,
      model_name: modelName,
      ...(apiKey ? { openai_api_key: apiKey } : {}),
      model_temperature: Number(temperature),
      model_max_tokens: Number(maxTokens),
      qwen_command: qwenCommand,
      qwen_model: qwenModel.trim() ? qwenModel.trim() : null,
      qwen_timeout_seconds: Number(qwenTimeout),
      qwen_auth_type: qwenAuthType.trim() ? qwenAuthType.trim() : null,
      qwen_approval_mode: qwenApprovalMode,
      qwen_use_sandbox: qwenUseSandbox
    };
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    update.mutate(settingsPayload());
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[320px_1fr]">
      <aside>
        <SystemStatusPanel />
      </aside>
      <main className="space-y-5">
        <Card>
          <div className="mb-5">
            <p className="text-xs uppercase tracking-[0.24em] text-ink-500 dark:text-ink-100">
              Model
            </p>
            <h1 className="font-display text-3xl font-bold">LLM endpoint</h1>
            <p className="mt-2 text-sm text-ink-500 dark:text-ink-100">
              Configure the OpenAI-compatible endpoint and model used by the analysis agent.
            </p>
          </div>
          <form className="grid gap-3" onSubmit={submit}>
            <div className="grid gap-3 lg:grid-cols-[1.3fr_1fr]">
              <Input
                aria-label="Base URL"
                placeholder="Base URL"
                value={llmBaseUrl}
                onChange={(event) => setLlmBaseUrl(event.target.value)}
              />
              <Input
                aria-label="Model name"
                placeholder="Model name"
                value={modelName}
                onChange={(event) => setModelName(event.target.value)}
              />
            </div>
            <div className="grid gap-3 lg:grid-cols-[1fr_120px_140px_auto]">
              <Input
                aria-label="API key"
                placeholder={
                  settings.data?.openai_api_key_configured
                    ? "API key configured; leave blank to keep it"
                    : "API key"
                }
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
              />
              <Input
                aria-label="Temperature"
                value={temperature}
                onChange={(event) => setTemperature(event.target.value)}
              />
              <Input
                aria-label="Max tokens"
                value={maxTokens}
                onChange={(event) => setMaxTokens(event.target.value)}
              />
              <Button disabled={update.isPending}>Save</Button>
            </div>
          </form>
          {update.error ? <p className="mt-3 text-sm text-red-600">{update.error.message}</p> : null}
        </Card>

        <Card>
          <div className="mb-5">
            <p className="text-xs uppercase tracking-[0.24em] text-ink-500 dark:text-ink-100">
              Analysis engine
            </p>
            <h2 className="font-display text-2xl font-bold">Intelligence Engine</h2>
            <p className="mt-2 text-sm text-ink-500 dark:text-ink-100">
              Choose whether chat requests use the managed SQL/LangGraph agent or an
              autonomous file-workspace engine against copied data files.
            </p>
          </div>
          <div className="mb-5 grid gap-3 md:grid-cols-2">
            <button
              className={`rounded-3xl border p-4 text-left transition ${
                analysisEngine === "standard"
                  ? "border-harbor-500 bg-harbor-50 shadow-soft dark:border-harbor-400 dark:bg-harbor-500/15"
                  : "border-ink-100 bg-white/60 hover:bg-white dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10"
              }`}
              onClick={() => setAnalysisEngine("standard")}
              type="button"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="font-semibold">Standard</span>
                {analysisEngine === "standard" ? (
                  <span className="rounded-full bg-harbor-500 px-2.5 py-1 text-xs font-semibold text-white">
                    Active
                  </span>
                ) : null}
              </div>
              <p className="mt-2 text-sm leading-6 text-ink-500 dark:text-ink-100">
                Uses the governed SQL-first LangGraph workflow with validation and bounded retries.
              </p>
            </button>
            <button
              className={`rounded-3xl border p-4 text-left transition ${
                analysisEngine === "qwen_cli"
                  ? "border-harbor-500 bg-harbor-50 shadow-soft dark:border-harbor-400 dark:bg-harbor-500/15"
                  : "border-ink-100 bg-white/60 hover:bg-white dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10"
              }`}
              onClick={() => {
                setAnalysisEngine("qwen_cli");
                setResponseMode("advanced");
              }}
              type="button"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="font-semibold">Advanced</span>
                {analysisEngine === "qwen_cli" ? (
                  <span className="rounded-full bg-harbor-500 px-2.5 py-1 text-xs font-semibold text-white">
                    Active
                  </span>
                ) : null}
              </div>
              <p className="mt-2 text-sm leading-6 text-ink-500 dark:text-ink-100">
                Runs an autonomous analysis engine inside a copied, data-only workspace
                and shows raw engine output in Advanced response mode.
              </p>
            </button>
          </div>
          <div className="mb-3">
            <Input
              aria-label="Engine executable path"
              placeholder="Engine executable path, for example /opt/homebrew/bin/qwen"
              value={qwenCommand}
              onChange={(event) => setQwenCommand(event.target.value)}
            />
            <p className="mt-2 text-xs leading-5 text-ink-500 dark:text-ink-100">
              Used only to start Advanced mode. This path is not shown in chat output.
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <Input
              aria-label="Engine timeout seconds"
              placeholder="Engine timeout seconds"
              value={qwenTimeout}
              onChange={(event) => setQwenTimeout(event.target.value)}
            />
            <Input
              aria-label="Engine auth type"
              placeholder="Engine auth type, e.g. openai"
              value={qwenAuthType}
              onChange={(event) => setQwenAuthType(event.target.value)}
            />
            <Input
              aria-label="Engine approval mode"
              placeholder="Engine approval mode"
              value={qwenApprovalMode}
              onChange={(event) => setQwenApprovalMode(event.target.value)}
            />
          </div>
          <label className="mt-4 flex items-center gap-3 rounded-2xl border border-ink-100 bg-white/50 p-3 text-sm dark:border-white/10 dark:bg-white/5">
            <input
              checked={qwenUseSandbox}
              onChange={(event) => setQwenUseSandbox(event.target.checked)}
              type="checkbox"
            />
            <span>
              Use the engine sandbox when the runtime supports it.
            </span>
          </label>
          <div className="mt-4 flex justify-end">
            <Button disabled={update.isPending} onClick={() => update.mutate(settingsPayload())}>
              Save engine settings
            </Button>
          </div>
        </Card>

        <Card>
          <div className="mb-5">
            <p className="text-xs uppercase tracking-[0.24em] text-ink-500 dark:text-ink-100">
              Response mode
            </p>
            <h2 className="font-display text-2xl font-bold">Answer detail level</h2>
            <p className="mt-2 text-sm text-ink-500 dark:text-ink-100">
              Choose how much audit detail the chat response shows to business users.
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <button
              className={`rounded-3xl border p-4 text-left transition ${
                responseMode === "simple"
                  ? "border-harbor-500 bg-harbor-50 shadow-soft dark:border-harbor-400 dark:bg-harbor-500/15"
                  : "border-ink-100 bg-white/60 hover:bg-white dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10"
              }`}
              onClick={() => setResponseMode("simple")}
              type="button"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="font-semibold">Simple</span>
                {responseMode === "simple" ? (
                  <span className="rounded-full bg-harbor-500 px-2.5 py-1 text-xs font-semibold text-white">
                    Active
                  </span>
                ) : null}
              </div>
              <p className="mt-2 text-sm leading-6 text-ink-500 dark:text-ink-100">
                Shows the final answer, summary, tables and charts while hiding SQL, Python, sources and caveats.
              </p>
            </button>
            <button
              className={`rounded-3xl border p-4 text-left transition ${
                responseMode === "advanced"
                  ? "border-harbor-500 bg-harbor-50 shadow-soft dark:border-harbor-400 dark:bg-harbor-500/15"
                  : "border-ink-100 bg-white/60 hover:bg-white dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10"
              }`}
              onClick={() => setResponseMode("advanced")}
              type="button"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="font-semibold">Advanced</span>
                {responseMode === "advanced" ? (
                  <span className="rounded-full bg-harbor-500 px-2.5 py-1 text-xs font-semibold text-white">
                    Active
                  </span>
                ) : null}
              </div>
              <p className="mt-2 text-sm leading-6 text-ink-500 dark:text-ink-100">
                Shows the full audit trail, including generated SQL or Python, source references and caveats.
              </p>
            </button>
          </div>
        </Card>

        <DataSourceManager />
        <SchemaBrowser />
      </main>
    </div>
  );
}
