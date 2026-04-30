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

function responseText(response) {
  const parts = [response.answer ?? "", response.reasoning_summary ?? "", response.sql_query ?? "", response.python_code ?? ""];
  for (const artifact of response.artifacts ?? []) {
    if (artifact.type === "table") {
      parts.push(artifact.title ?? "");
      parts.push((artifact.columns ?? []).join(" "));
      for (const row of artifact.rows ?? []) {
        parts.push(Object.values(row).join(" "));
      }
    }
    if (artifact.type === "chart") {
      parts.push(JSON.stringify(artifact.spec ?? artifact));
    }
  }
  return parts.join("\n").toLowerCase();
}

function hasTable(response) {
  return (response.artifacts ?? []).some((artifact) => artifact.type === "table" && (artifact.rows ?? []).length > 0);
}

function hasChart(response) {
  return (response.artifacts ?? []).some((artifact) => artifact.type === "chart");
}

function validate(test, response) {
  const text = responseText(response);
  const failures = [];
  const badPhrases = [
    "sql execution failed",
    "python execution failed",
    "could not retrieve",
    "unable to compute",
    "confirm the table schema",
    "access to the database",
    "no query was run",
    "actual data results were not provided",
    "table names may be incorrect",
  ];

  if (!test.allowLowConfidence && response.confidence === "low") {
    failures.push("returned low confidence");
  }
  const errorEvents = (response.status_events ?? []).filter((event) => event.status === "error");
  if (test.failOnIntermediateErrors && errorEvents.length) {
    failures.push(`status errors: ${errorEvents.map((event) => event.message).join(" | ")}`);
  }
  if (!test.allowFailureLanguage) {
    for (const phrase of badPhrases) {
      if (text.includes(phrase)) failures.push(`contains failure phrase: ${phrase}`);
    }
  }
  if (test.requiresSql && !response.sql_query) failures.push("missing SQL query");
  if (test.requiresTable && !hasTable(response)) failures.push("missing table artifact");
  if (test.requiresChart && !hasChart(response)) failures.push("missing chart artifact");
  for (const term of test.mustContain ?? []) {
    if (!text.includes(term.toLowerCase())) failures.push(`missing expected term: ${term}`);
  }
  for (const forbidden of test.mustNotContain ?? []) {
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

const tests = [
  {
    id: "manufacturing-warehouses-table-typo",
    sourceNames: ["qa_manufacturing_quality"],
    message: "what rea teh wear houses? show them in a table",
    requiresSql: true,
    requiresTable: true,
    mustContain: ["Dammam Hub", "Jubail Complex", "Rotterdam Terminal", "Houston Depot"],
  },
  {
    id: "manufacturing-low-stock-join",
    sourceNames: ["qa_manufacturing_quality"],
    message: "Which SKUs are below reorder point? Include warehouse name, supplier, and shortage amount.",
    requiresSql: true,
    requiresTable: true,
    mustContain: ["SC-100", "MT-510", "PL-330", "NovaChem", "Atlas Metals", "Rhine Compounds"],
    mustNotContain: ["PL-220"],
  },
  {
    id: "manufacturing-defect-rate",
    sourceNames: ["qa_manufacturing_quality"],
    message: "Which supplier country has the highest defect rate? Calculate defect_count divided by sample_size.",
    requiresSql: true,
    requiresTable: true,
    mustContain: ["United States", "0.088"],
  },
  {
    id: "retail-revenue-by-region",
    sourceNames: ["qa_retail_operations"],
    message: "For closed orders only, calculate total revenue by region sorted from highest to lowest.",
    requiresSql: true,
    requiresTable: true,
    mustContain: ["Middle East", "Europe", "15793", "13440"],
  },
  {
    id: "retail-target-comparison",
    sourceNames: ["qa_retail_operations"],
    message: "Compare monthly revenue to targets by region and show where performance is over or under target.",
    requiresSql: true,
    requiresTable: true,
    mustContain: ["target", "under", "over"],
  },
  {
    id: "people-overdue-training",
    sourceNames: ["qa_people_analytics"],
    message: "As of 2026-04-30, which employees have expired training, and what department are they in?",
    requiresSql: true,
    requiresTable: true,
    mustContain: ["Maya Chen", "Samir Khan", "Aisha Noor", "Jon Miller"],
  },
  {
    id: "people-absence-join",
    sourceNames: ["qa_people_analytics"],
    message: "Which department has the highest absence hours per employee? Show the calculation in a table.",
    requiresSql: true,
    requiresTable: true,
    mustContain: ["Supply Chain", "18"],
  },
  {
    id: "messy-highest-revenue",
    sourceNames: ["qa_messy_sales_export"],
    message: "In the messy Q2 sales export, which account has the highest revenue and what gross margin did it have?",
    requiresSql: true,
    requiresTable: true,
    mustContain: ["Sakura Labs", "31100", "0.3"],
  },
  {
    id: "csv-support-priority",
    sourceNames: ["qa_support_tickets"],
    message: "For support tickets, average resolution hours by priority and identify the open ticket with the longest resolution time.",
    requiresSql: true,
    requiresTable: true,
    mustContain: ["Critical", "42", "High", "36.5", "T-1005", "55"],
  },
  {
    id: "cross-source-high-revenue-open-ticket",
    sourceNames: ["qa_messy_sales_export", "qa_support_tickets"],
    message: "Across the sales export and support tickets, which customers have revenue above 20000 and an open support ticket? Show revenue, ticket priority, and owner.",
    requiresSql: true,
    requiresTable: true,
    mustContain: ["Desert Pearl", "Rhine Parts", "24500", "22100", "Critical", "High"],
    mustNotContain: ["Sakura Labs"],
  },
  {
    id: "retail-chart",
    sourceNames: ["qa_retail_operations"],
    message: "Create a chart-ready answer showing revenue by product category for closed orders.",
    requiresSql: true,
    requiresTable: true,
    mustContain: ["Materials", "Equipment", "Services", "Components"],
  },
  {
    id: "generic-question-suggestions",
    sourceNames: ["qa_retail_operations"],
    message: "What kind of questions can I ask about this data?",
    requiresTable: false,
    allowLowConfidence: false,
    allowErrors: true,
    mustContain: ["revenue", "customer", "product"],
    mustNotContain: ["here is the current data landscape", "precalculated summary metrics"],
  },
];

const filter = process.env.TEST_FILTER
  ? new Set(process.env.TEST_FILTER.split(",").map((item) => item.trim()).filter(Boolean))
  : null;
const selectedTests = filter ? tests.filter((test) => filter.has(test.id)) : tests;

const results = [];
for (const test of selectedTests) {
  const startedAt = Date.now();
  const selected = ids(test.sourceNames);
  let response;
  let failures = [];
  try {
    response = await request("/chat", {
      method: "POST",
      body: JSON.stringify({
        message: test.message,
        selected_data_sources: selected,
      }),
    });
    failures = validate(test, response);
  } catch (error) {
    failures = [error.stack ?? String(error)];
  }
  const result = {
    id: test.id,
    sourceNames: test.sourceNames,
    message: test.message,
    passed: failures.length === 0,
    failures,
    elapsed_seconds: Number(((Date.now() - startedAt) / 1000).toFixed(1)),
    confidence: response?.confidence,
    sql_query: response?.sql_query,
    python_code_present: Boolean(response?.python_code),
    artifact_types: (response?.artifacts ?? []).map((artifact) => artifact.type),
    status_events: response?.status_events,
    intermediate_errors: (response?.status_events ?? [])
      .filter((event) => event.status === "error")
      .map((event) => event.message),
    answer: response?.answer,
    caveats: response?.caveats,
  };
  results.push(result);
  console.log(`${result.passed ? "PASS" : "FAIL"} ${test.id} (${result.elapsed_seconds}s)`);
  if (!result.passed) console.log(JSON.stringify({ failures, answer: result.answer, sql_query: result.sql_query }, null, 2));
}

const report = {
  generated_at: new Date().toISOString(),
  filter: filter ? [...filter] : null,
  total: results.length,
  passed: results.filter((result) => result.passed).length,
  failed: results.filter((result) => !result.passed).length,
  results,
};
const reportPath = path.join(repoRoot, "Data", "qa_generated", "qa_chat_report.json");
await fs.writeFile(reportPath, JSON.stringify(report, null, 2));
console.log(JSON.stringify({ reportPath, total: report.total, passed: report.passed, failed: report.failed }, null, 2));
