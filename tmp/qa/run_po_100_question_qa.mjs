import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../..");
const apiBase = process.env.API_BASE ?? "http://127.0.0.1:8001";

async function request(pathname, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), Number(process.env.CHAT_TIMEOUT_MS ?? 210000));
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
  }
  return parts.join("\n").toLowerCase();
}

function hasTable(response) {
  return (response.artifacts ?? []).some(
    (artifact) =>
      artifact.type === "table" &&
      ((artifact.rows ?? []).length > 0 || (artifact.columns ?? []).length > 0)
  );
}

function validate(test, response) {
  const failures = [];
  const warnings = [];
  const text = responseText(response);
  const badPhrases = [
    "could not complete",
    "could not retrieve",
    "unable to compute",
    "cannot compute",
    "confirm the table schema",
    "access to the database",
    "no query was run",
    "please provide access",
    "python code generation failure",
    "sql execution failed",
    "actual data results were not provided",
  ];
  if (!response?.answer?.trim()) failures.push("empty answer");
  if (response.confidence === "low") failures.push("returned low confidence");
  if (test.requiresSql !== false && !response.sql_query && !response.python_code) {
    failures.push("missing generated SQL or Python logic");
  }
  const emptyResultAnswer =
    /(no .* found|no .* have|no .* has|no duplicate|no matching|0 rows|zero rows|returned 0 rows|none found)/i.test(
      response.answer ?? "",
    );
  if (test.requiresTable && !hasTable(response) && !(test.allowsEmptyResult && emptyResultAnswer)) {
    failures.push("missing table artifact");
  }
  for (const phrase of badPhrases) {
    if (text.includes(phrase)) failures.push(`contains failure phrase: ${phrase}`);
  }
  for (const term of test.mustContain ?? []) {
    if (!text.includes(term.toLowerCase())) failures.push(`missing expected term: ${term}`);
  }
  const intermediateErrors = (response.status_events ?? [])
    .filter((event) => event.status === "error")
    .map((event) => event.message);
  if (intermediateErrors.length) warnings.push(...intermediateErrors);
  return { failures, warnings };
}

const standaloneQuestions = [
  "What data is available in these two PO tables?",
  "Show row counts for both tables.",
  "List the columns and what each table appears to represent.",
  "What are the earliest and latest creation dates in each table?",
  "How many distinct purchase orders are in each table?",
  "How many distinct PO number and item combinations are in each table?",
  "Show the distinct company codes in both tables.",
  "Show distinct plants across both tables in a table.",
  "Which plants have missing values in either table?",
  "How many rows have missing plant values by table?",
  "Which function areas appear in the WBS table?",
  "Which function areas appear in the cost center table?",
  "Compare row counts by function area text across the two tables.",
  "Top 10 function areas by row count in the cost center table.",
  "Top 10 function areas by row count in the WBS table.",
  "Which function area has the most purchase order items overall?",
  "Show counts by company code and table.",
  "Show counts by plant and table, sorted highest first.",
  "Which plant has the most cost center rows?",
  "Which plant has the most WBS rows?",
  "Show yearly PO creation trend for both tables.",
  "Show monthly trend for 2026 in both tables.",
  "Which year has the highest number of PO items in the cost center table?",
  "Which year has the highest number of PO items in the WBS table?",
  "Show the latest 20 PO items from the cost center table.",
  "Show the latest 20 PO items from the WBS table.",
  "Show the oldest 20 PO items from both tables combined.",
  "Find duplicate PO number and item rows in the cost center table.",
  "Find duplicate PO number and item rows in the WBS table.",
  "Which PO numbers have the most line items in the cost center table?",
  "Which PO numbers have the most line items in the WBS table?",
  "How many PO item combinations exist in both tables?",
  "How many PO item combinations are only in the WBS table?",
  "How many PO item combinations are only in the cost center table?",
  "Show sample PO items that exist in both tables.",
  "Show sample PO items that exist only in the WBS table.",
  "Show sample PO items that exist only in the cost center table.",
  "Join the two tables on PO number and item and compare plant values.",
  "Find PO items where plant differs between the two tables.",
  "Find PO items where company code differs between the two tables.",
  "Find PO items where function area differs between the two tables.",
  "Find PO items where function area text differs between the two tables.",
  "Compare cost_center_wbs to cost_center for matching PO items.",
  "How many matching PO items have the same cost center and WBS cost center?",
  "How many matching PO items have different cost center and WBS cost center?",
  "Show the top cost centers by number of PO items.",
  "Show the top WBS cost centers by number of PO items.",
  "Which cost centers appear in both cost_center and cost_center_wbs?",
  "Which cost centers appear only as WBS cost centers?",
  "Which cost centers appear only as normal cost centers?",
  "Show function area distribution for cost centers that appear in both tables.",
  "Show plant distribution for PO items that appear in both tables.",
  "Which company code has the highest overlap between the two tables?",
  "Which plant has the highest overlap between the two tables?",
  "Show percentage overlap by company code between the two tables.",
  "Show percentage overlap by plant between the two tables.",
  "For company code 1000, show PO item counts by function area across both tables.",
  "For plant 1033, compare cost center and WBS rows by function area.",
  "For plant 1000, what are the top 10 cost centers?",
  "For plant 10M1, what function areas are represented?",
  "Show rows where func_area is missing in the cost center table.",
  "Show rows where func_area_txt is missing in the cost center table.",
  "Are there any missing func_area values in the WBS table?",
  "Find cost center rows where ekkn_kostl and cost_center are different.",
  "How many rows have ekkn_kostl different from cost_center by function area?",
  "Show the top plants where ekkn_kostl differs from cost_center.",
  "Show company code and plant combinations with the most rows.",
  "Which function area text maps to more than one function area code?",
  "Which function area code maps to more than one function area text?",
  "List all function area codes with their text labels.",
  "Show count of PO items by company code, plant, and year.",
  "Rank plants by number of distinct PO numbers.",
  "Rank function areas by number of distinct PO numbers.",
  "Show PO numbers that appear with more than five items.",
  "Show PO numbers that appear in both tables with more than three items.",
  "Find matching PO items created on different dates across the two tables.",
  "Find matching PO items where creation dates are the same.",
  "Show the date range by company code for each table.",
  "Show the date range by plant for each table.",
  "What are the most common PO item numbers in each table?",
  "Show cost center table counts by PO item number.",
  "Show WBS table counts by PO item number.",
  "Which PO item number has the highest overlap between tables?",
  "For Information Technology, compare rows by plant across both tables.",
  "For Manufacturing Support, compare rows by plant across both tables.",
  "For Corporate Affairs, show yearly trend in both tables.",
  "For Digitization, list the top cost centers and WBS cost centers.",
  "Which functional areas exist in WBS but not in cost center?",
  "Which functional areas exist in cost center but not in WBS?",
  "Show a data quality summary for both tables.",
  "Show a join quality summary between the two PO tables.",
  "What questions can I ask about these PO tables?",
  "Give me three executive insights from these two tables.",
];

const followUpSequences = [
  [
    "Show the top 5 plants by cost center row count.",
    "Now show the same plants from the WBS table.",
    "Compare those side by side and sort by the largest difference.",
    "Only show differences greater than 500 rows.",
  ],
  [
    "Which function areas have the most matching PO items across both tables?",
    "Now break the top function area down by plant.",
    "Show that as a chart-ready table sorted highest first.",
    "Now include company code in that breakdown.",
  ],
  [
    "Find PO item combinations where cost_center_wbs is different from cost_center.",
    "Show the top 10 mismatches by function area.",
    "Now only show company code 1000.",
    "For those results, summarize the data quality issue in plain language.",
  ],
  [
    "Show yearly counts for both tables.",
    "Now focus on the latest year only.",
    "Break that latest year down by month and table.",
    "Which month had the highest combined PO item count?",
  ],
  [
    "List PO numbers that appear in both tables with multiple items.",
    "Pick the PO with the most items and show its line details.",
    "Now compare its function areas across the two tables.",
    "Are there any inconsistencies for that PO?",
  ],
];

const tests = [];
for (const question of standaloneQuestions) {
  const isMetadataOnly = /what data is available|what questions can i ask|executive insights|list the columns|appears to represent/i.test(question);
  tests.push({
    question,
    group: null,
    requiresSql: !isMetadataOnly,
    requiresTable: !isMetadataOnly && /(show|list|rank|top|compare|find|which|how many|counts|trend|summary|distribution|percentage|range)/i.test(question),
    allowsEmptyResult: /(duplicate|different|differs|missing|only in|not in|mismatch|inconsistencies)/i.test(question),
  });
}
followUpSequences.forEach((sequence, sequenceIndex) => {
  sequence.forEach((question) => {
    tests.push({
      question,
      group: `followup-${sequenceIndex + 1}`,
      requiresSql: true,
      requiresTable: !/plain language|summarize|inconsistencies/i.test(question),
      allowsEmptyResult: /(duplicate|different|differs|missing|only in|not in|mismatch|inconsistencies)/i.test(question),
    });
  });
});

if (tests.length < 100) {
  throw new Error(`Expected at least 100 total questions, got ${tests.length}`);
}

const filterLimit = process.env.TEST_LIMIT ? Number(process.env.TEST_LIMIT) : null;
const filterNumbers = process.env.TEST_NUMBERS
  ? new Set(
      process.env.TEST_NUMBERS.split(",")
        .map((item) => Number(item.trim()))
        .filter((item) => Number.isInteger(item) && item > 0),
    )
  : null;
const selectedTests = filterNumbers
  ? tests.filter((_, index) => filterNumbers.has(index + 1))
  : filterLimit
    ? tests.slice(0, filterLimit)
    : tests;

const sources = await request("/datasources");
const poSources = sources.filter((source) =>
  ["po_with_wbs_element", "po_with_cost_center"].includes(source.name),
);
if (poSources.length !== 2) {
  throw new Error(`Expected the two PO sources to be registered; found ${poSources.length}`);
}
const selected_data_sources = poSources.map((source) => source.id);

const conversationByGroup = new Map();
const results = [];
for (let index = 0; index < selectedTests.length; index += 1) {
  const test = selectedTests[index];
  const startedAt = Date.now();
  let response;
  let failures = [];
  let warnings = [];
  try {
    const conversation_id = test.group ? conversationByGroup.get(test.group) ?? null : null;
    response = await request("/chat", {
      method: "POST",
      body: JSON.stringify({
        message: test.question,
        conversation_id,
        selected_data_sources,
      }),
    });
    if (test.group) conversationByGroup.set(test.group, response.conversation_id);
    const validation = validate(test, response);
    failures = validation.failures;
    warnings = validation.warnings;
  } catch (error) {
    failures = [error.stack ?? String(error)];
  }
  const result = {
    number: index + 1,
    question: test.question,
    group: test.group,
    passed: failures.length === 0,
    failures,
    warnings,
    elapsed_seconds: Number(((Date.now() - startedAt) / 1000).toFixed(1)),
    confidence: response?.confidence,
    sql_query: response?.sql_query,
    python_code_present: Boolean(response?.python_code),
    artifact_types: (response?.artifacts ?? []).map((artifact) => artifact.type),
    answer: response?.answer,
    status_events: response?.status_events,
  };
  results.push(result);
  console.log(`${result.passed ? "PASS" : "FAIL"} ${result.number}/${selectedTests.length}: ${test.question} (${result.elapsed_seconds}s)`);
  if (!result.passed) {
    console.log(JSON.stringify({ failures, answer: result.answer, sql_query: result.sql_query }, null, 2));
  }
}

const report = {
  generated_at: new Date().toISOString(),
  selected_sources: poSources.map((source) => ({ id: source.id, name: source.name, path: source.path })),
  total_questions: results.length,
  passed: results.filter((result) => result.passed).length,
  failed: results.filter((result) => !result.passed).length,
  warning_count: results.reduce((sum, result) => sum + result.warnings.length, 0),
  questions: results.map((result) => result.question),
  results,
};
const outputDir = path.join(repoRoot, "Data", "po_synthetic");
await fs.writeFile(path.join(outputDir, "po_100_question_report.json"), JSON.stringify(report, null, 2));
const md = [
  "# PO Synthetic 100+ Question QA Report",
  "",
  `Generated: ${report.generated_at}`,
  `Total questions: ${report.total_questions}`,
  `Passed: ${report.passed}`,
  `Failed: ${report.failed}`,
  `Warnings: ${report.warning_count}`,
  "",
  "## Questions Asked",
  "",
  ...report.questions.map((question, idx) => `${idx + 1}. ${question}`),
  "",
  "## Failures",
  "",
  ...(report.results.filter((result) => !result.passed).length
    ? report.results
        .filter((result) => !result.passed)
        .map((result) => `- ${result.number}. ${result.question}: ${result.failures.join("; ")}`)
    : ["No failures."]),
  "",
].join("\n");
await fs.writeFile(path.join(outputDir, "po_100_question_report.md"), md, "utf8");

console.log(
  JSON.stringify(
    {
      report_json: path.join(outputDir, "po_100_question_report.json"),
      report_md: path.join(outputDir, "po_100_question_report.md"),
      total_questions: report.total_questions,
      passed: report.passed,
      failed: report.failed,
      warning_count: report.warning_count,
    },
    null,
    2,
  ),
);
