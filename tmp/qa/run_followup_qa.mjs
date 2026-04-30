import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../..");
const apiBase = process.env.API_BASE ?? "http://127.0.0.1:8001";

async function request(pathname, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), Number(process.env.CHAT_TIMEOUT_MS ?? 180000));
  try {
    const response = await fetch(`${apiBase}${pathname}`, {
      ...options,
      signal: controller.signal,
      headers: {
        "content-type": "application/json",
        ...(options.headers ?? {}),
      },
    });
    const text = await response.text();
    if (!response.ok) {
      throw new Error(`${options.method ?? "GET"} ${pathname} failed: ${response.status} ${text}`);
    }
    return text ? JSON.parse(text) : null;
  } finally {
    clearTimeout(timeout);
  }
}

function joinedResponseText(response) {
  const parts = [response.answer ?? "", response.reasoning_summary ?? "", response.sql_query ?? "", response.python_code ?? ""];
  for (const artifact of response.artifacts ?? []) {
    if (artifact.type === "table") {
      parts.push(artifact.title ?? "");
      parts.push((artifact.columns ?? []).join(" "));
      for (const row of artifact.rows ?? []) {
        parts.push(Object.values(row).join(" "));
      }
    }
  }
  return parts.join("\n").toLowerCase();
}

function hasTable(response) {
  return (response.artifacts ?? []).some((artifact) => artifact.type === "table" && (artifact.rows ?? []).length > 0);
}

function validateStep(step, response) {
  const text = joinedResponseText(response);
  const failures = [];
  const badPhrases = [
    "could not complete",
    "could not retrieve",
    "unable to compute",
    "confirm the table schema",
    "access to the database",
    "no query was run",
    "please provide access",
    "python code generation failure",
  ];
  if (response.confidence === "low") failures.push("returned low confidence");
  const errorEvents = (response.status_events ?? []).filter((event) => event.status === "error");
  if (step.failOnIntermediateErrors && errorEvents.length) {
    failures.push(`status errors: ${errorEvents.map((event) => event.message).join(" | ")}`);
  }
  if (step.requiresSql && !response.sql_query) failures.push("missing SQL query");
  if (step.requiresTable && !hasTable(response)) failures.push("missing table artifact");
  for (const phrase of badPhrases) {
    if (text.includes(phrase)) failures.push(`contains failure phrase: ${phrase}`);
  }
  for (const term of step.mustContain ?? []) {
    if (!text.includes(term.toLowerCase())) failures.push(`missing expected term: ${term}`);
  }
  for (const forbidden of step.mustNotContain ?? []) {
    if (text.includes(forbidden.toLowerCase())) failures.push(`included forbidden term: ${forbidden}`);
  }
  return failures;
}

const sources = await request("/datasources");
const sourceByName = new Map(sources.map((source) => [source.name, source]));
function ids(names) {
  return names.map((name) => {
    const source = sourceByName.get(name);
    if (!source) throw new Error(`Missing data source ${name}`);
    return source.id;
  });
}

const sequences = [
  {
    id: "manufacturing-low-stock-followups",
    sourceNames: ["qa_manufacturing_quality"],
    steps: [
      {
        message: "Which SKUs are below reorder point?",
        requiresSql: true,
        requiresTable: true,
        mustContain: ["SC-100", "MT-510", "PL-330"],
      },
      {
        message: "Show the supplier and warehouse details for those, highest shortage first.",
        requiresSql: true,
        requiresTable: true,
        mustContain: ["Rhine Compounds", "Atlas Metals", "NovaChem", "Rotterdam Terminal", "Houston Depot", "Dammam Hub"],
      },
      {
        message: "Now only show the high-risk supplier items.",
        requiresSql: true,
        requiresTable: true,
        mustContain: ["MT-510", "Atlas Metals", "High"],
        mustNotContain: ["PL-330"],
      },
    ],
  },
  {
    id: "retail-revenue-followups",
    sourceNames: ["qa_retail_operations"],
    steps: [
      {
        message: "Show revenue by region for closed orders.",
        requiresSql: true,
        requiresTable: true,
        mustContain: ["Middle East", "15793"],
      },
      {
        message: "Now break the highest region down by product category.",
        requiresSql: true,
        requiresTable: true,
        mustContain: ["Middle East", "Materials", "Components"],
      },
      {
        message: "Put that in a chart-ready table sorted highest first.",
        requiresSql: true,
        requiresTable: true,
        mustContain: ["Materials", "Components"],
      },
    ],
  },
  {
    id: "messy-renewal-followups",
    sourceNames: ["qa_messy_sales_export"],
    steps: [
      {
        message: "Which accounts have revenue above 20000?",
        requiresSql: true,
        requiresTable: true,
        mustContain: ["Desert Pearl", "Sakura Labs", "Rhine Parts"],
      },
      {
        message: "Of those, which have renewal health scores below 70?",
        requiresSql: true,
        requiresTable: true,
        mustContain: ["Desert Pearl", "64"],
      },
    ],
  },
  {
    id: "people-risk-followups",
    sourceNames: ["qa_people_analytics"],
    steps: [
      {
        message: "Which employees have expired training as of 2026-04-30?",
        requiresSql: true,
        requiresTable: true,
        mustContain: ["Maya Chen", "Samir Khan", "Aisha Noor", "Jon Miller"],
      },
      {
        message: "Now show only those with high risk_flag or performance below 3.2.",
        requiresSql: true,
        requiresTable: true,
        mustContain: ["Jon Miller", "Samir Khan"],
        mustNotContain: ["Maya Chen"],
      },
    ],
  },
];

const filter = process.env.SEQUENCE_FILTER
  ? new Set(process.env.SEQUENCE_FILTER.split(",").map((item) => item.trim()).filter(Boolean))
  : null;
const selectedSequences = filter
  ? sequences.filter((sequence) => filter.has(sequence.id))
  : sequences;

const results = [];
for (const sequence of selectedSequences) {
  let conversationId = null;
  const selected = ids(sequence.sourceNames);
  const stepResults = [];
  for (let index = 0; index < sequence.steps.length; index += 1) {
    const step = sequence.steps[index];
    const startedAt = Date.now();
    let response;
    let failures = [];
    try {
      response = await request("/chat", {
        method: "POST",
        body: JSON.stringify({
          message: step.message,
          conversation_id: conversationId,
          selected_data_sources: selected,
        }),
      });
      conversationId = response.conversation_id;
      failures = validateStep(step, response);
    } catch (error) {
      failures = [error.stack ?? String(error)];
    }
    const result = {
      step: index + 1,
      message: step.message,
      passed: failures.length === 0,
      failures,
      elapsed_seconds: Number(((Date.now() - startedAt) / 1000).toFixed(1)),
      confidence: response?.confidence,
      sql_query: response?.sql_query,
      artifact_types: (response?.artifacts ?? []).map((artifact) => artifact.type),
      answer: response?.answer,
      status_events: response?.status_events,
      intermediate_errors: (response?.status_events ?? [])
        .filter((event) => event.status === "error")
        .map((event) => event.message),
    };
    stepResults.push(result);
    console.log(`${result.passed ? "PASS" : "FAIL"} ${sequence.id} step ${index + 1} (${result.elapsed_seconds}s)`);
    if (!result.passed) {
      console.log(JSON.stringify({ failures, answer: result.answer, sql_query: result.sql_query }, null, 2));
      break;
    }
  }
  results.push({
    id: sequence.id,
    sourceNames: sequence.sourceNames,
    conversation_id: conversationId,
    passed: stepResults.every((step) => step.passed) && stepResults.length === sequence.steps.length,
    steps: stepResults,
  });
}

const report = {
  generated_at: new Date().toISOString(),
  total_sequences: results.length,
  passed_sequences: results.filter((result) => result.passed).length,
  failed_sequences: results.filter((result) => !result.passed).length,
  results,
};
const reportPath = path.join(repoRoot, "Data", "qa_generated", "qa_followup_report.json");
await fs.writeFile(reportPath, JSON.stringify(report, null, 2));
console.log(JSON.stringify({ reportPath, total_sequences: report.total_sequences, passed_sequences: report.passed_sequences, failed_sequences: report.failed_sequences }, null, 2));
