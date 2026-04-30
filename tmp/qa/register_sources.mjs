import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../..");
const manifest = JSON.parse(
  await fs.readFile(path.join(repoRoot, "Data", "qa_generated", "qa_manifest.json"), "utf8"),
);

const apiBase = process.env.API_BASE ?? "http://127.0.0.1:8001";
const sourceTypeByExt = new Map([
  [".csv", "csv"],
  [".xlsx", "excel"],
  [".xlsm", "excel"],
  [".xls", "excel"],
  [".sqlite", "sqlite"],
  [".sqlite3", "sqlite"],
  [".db", "sqlite"],
]);

async function request(pathname, options = {}) {
  const response = await fetch(`${apiBase}${pathname}`, {
    ...options,
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
}

const existing = await request("/datasources");
const byPath = new Map(existing.map((source) => [path.resolve(source.path), source]));
const registered = [];

for (const filePath of manifest.files) {
  const absolutePath = path.resolve(filePath);
  const ext = path.extname(absolutePath).toLowerCase();
  const sourceType = sourceTypeByExt.get(ext);
  if (!sourceType) continue;

  let source = byPath.get(absolutePath);
  if (!source) {
    const name = path.basename(absolutePath, ext);
    source = await request("/datasources", {
      method: "POST",
      body: JSON.stringify({ name, source_type: sourceType, path: absolutePath }),
    });
  }
  registered.push(source);
}

const rescanned = await request("/datasources/rescan", {
  method: "POST",
  body: JSON.stringify({ source_ids: registered.map((source) => source.id), force: true }),
});

console.log(
  JSON.stringify(
    {
      registered: rescanned.map((source) => ({
        id: source.id,
        name: source.name,
        type: source.source_type,
        status: source.status,
        error: source.error,
      })),
    },
    null,
    2,
  ),
);
