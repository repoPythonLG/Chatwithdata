import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../..");
const apiBase = process.env.API_BASE ?? "http://127.0.0.1:8001";
const manifest = JSON.parse(
  await fs.readFile(path.join(repoRoot, "Data", "po_synthetic", "po_synthetic_manifest.json"), "utf8"),
);

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
  let source = byPath.get(absolutePath);
  if (!source) {
    source = await request("/datasources", {
      method: "POST",
      body: JSON.stringify({
        name: path.basename(absolutePath, ".csv"),
        source_type: "csv",
        path: absolutePath,
      }),
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
        path: source.path,
        status: source.status,
        error: source.error,
      })),
    },
    null,
    2,
  ),
);
