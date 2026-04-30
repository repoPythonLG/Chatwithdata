import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../..");
const outputDir = path.join(repoRoot, "Data", "po_synthetic");

const funcAreas = [
  [9, "Executive Office"],
  [10, "Finance"],
  [12, "Information Technology"],
  [14, "SS Facility Mgt"],
  [15, "EHSS"],
  [17, "Technology & Innovation"],
  [20, "Legal"],
  [23, "Corporate Affairs"],
  [25, "Human Resources"],
  [27, "Manufacturing Support"],
  [28, "SS Global Procurement"],
  [30, "Digitization"],
  [32, "Supply Chain"],
  [35, "Sales & Marketing"],
];

const plants = ["1000", "1031", "1033", "10M1", "10M2", "1100", "2100", "3200", "4100"];
const companyCodes = [1000, 2000, 3000, 4100];
const seededWbsRows = [
  [4506480584, 10, 1000, "10M1", 20260119, 1027005, 27, "Manufacturing Support"],
  [4506574981, 10, 1000, "1000", 20260419, 1012870, 12, "Information Technology"],
  [4802464288, 10, 1000, "1000", 20260406, 1017044, 17, "Technology & Innovation"],
  [4506577975, 10, 1000, "1000", 20260423, 1012870, 12, "Information Technology"],
  [4802399814, 20, 1000, "1000", 20250806, 1030005, 30, "Digitization"],
  [4802468315, 10, 1000, "1000", 20260427, 1030005, 30, "Digitization"],
  [4802468318, 10, 1000, "1000", 20260427, 1009001, 9, "Executive Office"],
  [4506580378, 10, 1000, "1000", 20260427, 1009001, 9, "Executive Office"],
  [4200000298, 10, 1000, "1000", 20080217, 1014500, 23, "Corporate Affairs"],
  [4200000298, 20, 1000, "1000", 20080217, 1014500, 23, "Corporate Affairs"],
  [4200000308, 10, 1000, "1000", 20080223, 1017023, 17, "Technology & Innovation"],
  [4200000543, 10, 1000, "1000", 20080715, 1014500, 23, "Corporate Affairs"],
  [4200000543, 20, 1000, "1000", 20080715, 1014500, 23, "Corporate Affairs"],
  [4200000543, 30, 1000, "1000", 20080715, 1014500, 23, "Corporate Affairs"],
  [4200000709, 10, 1000, "1000", 20080908, 1014500, 23, "Corporate Affairs"],
];
const seededCostCenterRows = [
  [4801242967, 10, 1000, "1000", 20170102, 1012843, 1012843, 12, "Information Technology"],
  [4801243122, 10, 1000, "1033", 20170103, 1013614, 1013614, 28, "SS Global Procurement"],
  [4801243207, 10, 1000, "1000", 20170103, 1014501, 1014501, 14, "SS Facility Mgt"],
  [4801243212, 10, 1000, "1033", 20170103, 1012876, 1012876, 12, "Information Technology"],
  [4801243643, 30, 1000, "1000", 20170104, 1010670, 1010670, 10, "Finance"],
  [4801243643, 20, 1000, "1000", 20170104, 1010670, 1010670, 10, "Finance"],
  [4801243643, 10, 1000, "1000", 20170104, 1010670, 1010670, 10, "Finance"],
  [4801243691, 10, 1000, "1031", 20170104, 1001023, 1001023, 27, "Manufacturing Support"],
  [4801243694, 10, 1000, "1031", 20170104, 1001023, 1001023, 27, "Manufacturing Support"],
  [4801243697, 10, 1000, "1033", 20170104, 1013630, 1013630, 28, "SS Global Procurement"],
  [4801243769, 10, 1000, "1033", 20170104, 1013614, 1013614, 28, "SS Global Procurement"],
  [4801243872, 10, 1000, "1033", 20170104, 1012876, 1012876, 12, "Information Technology"],
  [4801243947, 10, 1000, "1033", 20170104, 1015501, 1015501, 15, "EHSS"],
  [4801243963, 10, 1000, "1033", 20170104, 1012914, 1012914, 12, "Information Technology"],
  [4801243965, 10, 1000, "1033", 20170104, 1017085, 1017085, 17, "Technology & Innovation"],
];

function lcg(seed) {
  let value = seed >>> 0;
  return () => {
    value = (1664525 * value + 1013904223) >>> 0;
    return value / 2 ** 32;
  };
}

const rand = lcg(20260430);

function pick(items) {
  return items[Math.floor(rand() * items.length)];
}

function yyyymmdd(year, month, day) {
  return year * 10000 + month * 100 + day;
}

function randomDateInt() {
  const year = 2017 + Math.floor(rand() * 10);
  const month = 1 + Math.floor(rand() * 12);
  const day = 1 + Math.floor(rand() * 28);
  return yyyymmdd(year, month, day);
}

function areaForIndex(index) {
  if (index % 11 === 0) return [12, "Information Technology"];
  if (index % 13 === 0) return [27, "Manufacturing Support"];
  if (index % 17 === 0) return [28, "SS Global Procurement"];
  if (index % 19 === 0) return [30, "Digitization"];
  return pick(funcAreas);
}

function costCenterFor(areaCode, variant = 0) {
  return 1000000 + areaCode * 1000 + ((variant * 37) % 900);
}

function csvEscape(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  if (/[",\n]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}

async function writeCsv(filePath, headers, rows) {
  const lines = [headers.join(",")];
  for (const row of rows) {
    lines.push(row.map(csvEscape).join(","));
  }
  await fs.writeFile(filePath, `${lines.join("\n")}\n`, "utf8");
}

await fs.mkdir(outputDir, { recursive: true });

const costRows = [...seededCostCenterRows];
const wbsRows = [...seededWbsRows];
const sharedKeys = [];

for (let i = 0; i < 52000; i += 1) {
  const poNumber = 4805000000 + Math.floor(i / 4);
  const poItem = [10, 20, 30, 40, 50, 60, 70, 80][i % 8];
  const companyCode = companyCodes[i % companyCodes.length];
  const [funcArea, funcAreaTxt] = areaForIndex(i);
  const creationDate = randomDateInt();
  const ekknKostl = costCenterFor(funcArea, i);
  const mismatch = i % 97 === 0;
  const costCenter = mismatch ? costCenterFor(pick(funcAreas)[0], i + 5) : ekknKostl;
  const plant = i % 811 === 0 ? "" : pick(plants);
  const missingFunc = i % 1777 === 0;
  costRows.push([
    poNumber,
    poItem,
    companyCode,
    plant,
    creationDate,
    ekknKostl,
    costCenter,
    missingFunc ? "" : funcArea,
    missingFunc ? "" : funcAreaTxt,
  ]);
  if (i % 3 === 0) {
    sharedKeys.push({
      poNumber,
      poItem,
      companyCode,
      plant,
      creationDate,
      funcArea,
      funcAreaTxt,
      costCenter,
    });
  }
}

for (let i = 0; i < 18000; i += 1) {
  const useShared = i < sharedKeys.length && i % 5 !== 0;
  const shared = useShared ? sharedKeys[i] : null;
  const poNumber = shared?.poNumber ?? 4509000000 + Math.floor(i / 3);
  const poItem = shared?.poItem ?? [10, 20, 30, 40, 50, 60, 70, 80][i % 8];
  const companyCode = shared?.companyCode ?? companyCodes[(i + 1) % companyCodes.length];
  const [funcArea, funcAreaTxt] = shared ? [shared.funcArea, shared.funcAreaTxt] : areaForIndex(i + 101);
  const creationDate = shared?.creationDate ?? randomDateInt();
  const plant = i % 607 === 0 ? "" : (shared?.plant || pick(plants));
  const costCenterWbs = i % 83 === 0
    ? costCenterFor(pick(funcAreas)[0], i + 9)
    : (shared?.costCenter ?? costCenterFor(funcArea, i + 3));
  wbsRows.push([
    poNumber,
    poItem,
    companyCode,
    plant,
    creationDate,
    costCenterWbs,
    funcArea,
    funcAreaTxt,
  ]);
}

const wbsPath = path.join(outputDir, "po_with_wbs_element.csv");
const costPath = path.join(outputDir, "po_with_cost_center.csv");

await writeCsv(
  wbsPath,
  [
    "po_number",
    "po_item",
    "company_code",
    "plant",
    "creation_date",
    "cost_center_wbs",
    "func_area",
    "func_area_txt",
  ],
  wbsRows,
);

await writeCsv(
  costPath,
  [
    "po_number",
    "po_item",
    "company_code",
    "plant",
    "creation_date",
    "ekkn_kostl",
    "cost_center",
    "func_area",
    "func_area_txt",
  ],
  costRows,
);

const manifest = {
  generated_at: new Date().toISOString(),
  files: [wbsPath, costPath],
  row_counts: {
    po_with_wbs_element: wbsRows.length,
    po_with_cost_center: costRows.length,
  },
  relationship_hints: [
    "po_number + po_item links the two tables when the same purchase order item is represented by WBS element and cost center data.",
    "cost_center_wbs can be compared with cost_center for overlap/mismatch analysis.",
    "func_area and func_area_txt can be compared across both tables for consistency.",
  ],
};
await fs.writeFile(path.join(outputDir, "po_synthetic_manifest.json"), JSON.stringify(manifest, null, 2));
console.log(JSON.stringify(manifest, null, 2));
