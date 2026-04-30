import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../..");
const outputDir = path.join(repoRoot, "Data", "qa_generated");

function colName(index) {
  let name = "";
  let n = index + 1;
  while (n > 0) {
    const rem = (n - 1) % 26;
    name = String.fromCharCode(65 + rem) + name;
    n = Math.floor((n - 1) / 26);
  }
  return name;
}

function writeRecords(sheet, startCell, headers, records) {
  const match = startCell.match(/^([A-Z]+)([0-9]+)$/);
  if (!match) throw new Error(`Invalid start cell ${startCell}`);
  const startCol = match[1].charCodeAt(0) - 65;
  const startRow = Number(match[2]);
  const rows = [headers, ...records.map((record) => headers.map((header) => record[header] ?? null))];
  const endCol = colName(startCol + headers.length - 1);
  const endRow = startRow + rows.length - 1;
  sheet.getRange(`${startCell}:${endCol}${endRow}`).values = rows;
}

async function saveWorkbook(fileName, sheets) {
  const workbook = Workbook.create();
  for (const [sheetName, spec] of Object.entries(sheets)) {
    const sheet = workbook.worksheets.add(sheetName);
    if (spec.notes) {
      sheet.getRange("A1:A2").values = spec.notes.map((note) => [note]);
    }
    writeRecords(sheet, spec.startCell ?? "A1", spec.headers, spec.records);
  }
  const output = await SpreadsheetFile.exportXlsx(workbook);
  const filePath = path.join(outputDir, fileName);
  await output.save(filePath);
  return filePath;
}

const retail = {
  Customers: {
    headers: ["customer_id", "customer_name", "region", "segment", "signup_date"],
    records: [
      { customer_id: 1, customer_name: "Acme Mobility", region: "Europe", segment: "Enterprise", signup_date: "2025-09-12" },
      { customer_id: 2, customer_name: "Gulf Retail", region: "Middle East", segment: "SMB", signup_date: "2025-11-03" },
      { customer_id: 3, customer_name: "Pacific Robotics", region: "Asia", segment: "Enterprise", signup_date: "2025-10-19" },
      { customer_id: 4, customer_name: "Northwind Industrial", region: "Europe", segment: "Mid-Market", signup_date: "2025-12-01" },
      { customer_id: 5, customer_name: "Atlas Mining", region: "North America", segment: "Enterprise", signup_date: "2026-01-07" },
      { customer_id: 6, customer_name: "Oasis Healthcare", region: "Middle East", segment: "Mid-Market", signup_date: "2026-02-13" },
    ],
  },
  Products: {
    headers: ["product_id", "product_name", "category", "unit_price", "unit_cost", "active"],
    records: [
      { product_id: "P100", product_name: "Industrial Pump", category: "Equipment", unit_price: 1200, unit_cost: 760, active: true },
      { product_id: "P200", product_name: "IoT Sensor", category: "Components", unit_price: 180, unit_cost: 90, active: true },
      { product_id: "P300", product_name: "Polymer Resin", category: "Materials", unit_price: 420, unit_cost: 260, active: true },
      { product_id: "P400", product_name: "Service Kit", category: "Services", unit_price: 650, unit_cost: 300, active: true },
      { product_id: "P500", product_name: "Catalyst Pack", category: "Materials", unit_price: 950, unit_cost: 640, active: false },
    ],
  },
  Orders: {
    headers: ["order_id", "customer_id", "order_date", "channel", "status"],
    records: [
      { order_id: 1001, customer_id: 1, order_date: "2026-01-05", channel: "Online", status: "Closed" },
      { order_id: 1002, customer_id: 2, order_date: "2026-01-14", channel: "Partner", status: "Closed" },
      { order_id: 1003, customer_id: 1, order_date: "2026-02-03", channel: "Direct", status: "Closed" },
      { order_id: 1004, customer_id: 3, order_date: "2026-02-18", channel: "Online", status: "Open" },
      { order_id: 1005, customer_id: 4, order_date: "2026-03-10", channel: "Direct", status: "Closed" },
      { order_id: 1006, customer_id: 5, order_date: "2026-03-12", channel: "Partner", status: "Closed" },
      { order_id: 1007, customer_id: 6, order_date: "2026-04-04", channel: "Direct", status: "Closed" },
      { order_id: 1008, customer_id: 2, order_date: "2026-04-18", channel: "Online", status: "Closed" },
      { order_id: 1009, customer_id: 3, order_date: "2026-04-22", channel: "Direct", status: "Closed" },
    ],
  },
  OrderLines: {
    headers: ["line_id", "order_id", "product_id", "quantity", "discount_pct"],
    records: [
      { line_id: "L1", order_id: 1001, product_id: "P100", quantity: 2, discount_pct: 0.05 },
      { line_id: "L2", order_id: 1001, product_id: "P200", quantity: 10, discount_pct: 0 },
      { line_id: "L3", order_id: 1002, product_id: "P300", quantity: 20, discount_pct: 0.02 },
      { line_id: "L4", order_id: 1003, product_id: "P500", quantity: 4, discount_pct: 0.1 },
      { line_id: "L5", order_id: 1004, product_id: "P200", quantity: 30, discount_pct: 0 },
      { line_id: "L6", order_id: 1005, product_id: "P400", quantity: 3, discount_pct: 0 },
      { line_id: "L7", order_id: 1005, product_id: "P300", quantity: 10, discount_pct: 0.05 },
      { line_id: "L8", order_id: 1006, product_id: "P100", quantity: 1, discount_pct: 0 },
      { line_id: "L9", order_id: 1006, product_id: "P500", quantity: 2, discount_pct: 0 },
      { line_id: "L10", order_id: 1007, product_id: "P300", quantity: 12, discount_pct: 0.03 },
      { line_id: "L11", order_id: 1008, product_id: "P200", quantity: 15, discount_pct: 0.01 },
      { line_id: "L12", order_id: 1009, product_id: "P400", quantity: 2, discount_pct: 0 },
    ],
  },
  Returns: {
    headers: ["return_id", "order_id", "product_id", "return_date", "quantity", "reason"],
    records: [
      { return_id: "R1", order_id: 1002, product_id: "P300", return_date: "2026-01-30", quantity: 2, reason: "Damaged" },
      { return_id: "R2", order_id: 1006, product_id: "P500", return_date: "2026-03-25", quantity: 1, reason: "Wrong item" },
      { return_id: "R3", order_id: 1008, product_id: "P200", return_date: "2026-04-28", quantity: 3, reason: "Defective" },
    ],
  },
  Targets: {
    headers: ["month", "region", "target_revenue"],
    records: [
      { month: "2026-01-01", region: "Europe", target_revenue: 4500 },
      { month: "2026-01-01", region: "Middle East", target_revenue: 9000 },
      { month: "2026-02-01", region: "Europe", target_revenue: 3500 },
      { month: "2026-02-01", region: "Asia", target_revenue: 6000 },
      { month: "2026-03-01", region: "Europe", target_revenue: 5000 },
      { month: "2026-03-01", region: "North America", target_revenue: 3000 },
      { month: "2026-04-01", region: "Middle East", target_revenue: 8500 },
      { month: "2026-04-01", region: "Asia", target_revenue: 4000 },
    ],
  },
};

const manufacturing = {
  Warehouses: {
    headers: ["warehouse_id", "warehouse_name", "city", "region", "capacity_tons"],
    records: [
      { warehouse_id: "W1", warehouse_name: "Dammam Hub", city: "Dammam", region: "Middle East", capacity_tons: 700 },
      { warehouse_id: "W2", warehouse_name: "Jubail Complex", city: "Jubail", region: "Middle East", capacity_tons: 900 },
      { warehouse_id: "W3", warehouse_name: "Rotterdam Terminal", city: "Rotterdam", region: "Europe", capacity_tons: 650 },
      { warehouse_id: "W4", warehouse_name: "Houston Depot", city: "Houston", region: "North America", capacity_tons: 500 },
    ],
  },
  Inventory: {
    headers: ["sku", "material_family", "warehouse_id", "quantity_tons", "reorder_point", "unit_cost"],
    records: [
      { sku: "SC-100", material_family: "Specialty Chemicals", warehouse_id: "W1", quantity_tons: 84, reorder_point: 90, unit_cost: 1120 },
      { sku: "PL-220", material_family: "Polymers", warehouse_id: "W2", quantity_tons: 210, reorder_point: 180, unit_cost: 860 },
      { sku: "AG-310", material_family: "Agri-Nutrients", warehouse_id: "W1", quantity_tons: 118, reorder_point: 100, unit_cost: 310 },
      { sku: "MT-510", material_family: "Metals", warehouse_id: "W4", quantity_tons: 32, reorder_point: 45, unit_cost: 2200 },
      { sku: "PL-330", material_family: "Polymers", warehouse_id: "W3", quantity_tons: 55, reorder_point: 80, unit_cost: 450 },
      { sku: "CX-710", material_family: "Catalysts", warehouse_id: "W2", quantity_tons: 76, reorder_point: 65, unit_cost: 1280 },
    ],
  },
  Suppliers: {
    headers: ["supplier_id", "sku", "supplier_name", "country", "lead_time_days", "risk_rating"],
    records: [
      { supplier_id: "S1", sku: "SC-100", supplier_name: "NovaChem", country: "Germany", lead_time_days: 21, risk_rating: "Low" },
      { supplier_id: "S2", sku: "PL-220", supplier_name: "Gulf Polymers", country: "Saudi Arabia", lead_time_days: 12, risk_rating: "Medium" },
      { supplier_id: "S3", sku: "AG-310", supplier_name: "Harvest Inputs", country: "India", lead_time_days: 18, risk_rating: "Medium" },
      { supplier_id: "S4", sku: "MT-510", supplier_name: "Atlas Metals", country: "United States", lead_time_days: 30, risk_rating: "High" },
      { supplier_id: "S5", sku: "PL-330", supplier_name: "Rhine Compounds", country: "Netherlands", lead_time_days: 16, risk_rating: "Low" },
      { supplier_id: "S6", sku: "CX-710", supplier_name: "Jubail Catalysts", country: "Saudi Arabia", lead_time_days: 10, risk_rating: "Low" },
    ],
  },
  QualityInspections: {
    headers: ["inspection_id", "sku", "inspection_date", "sample_size", "defect_count", "disposition"],
    records: [
      { inspection_id: 501, sku: "SC-100", inspection_date: "2026-01-10", sample_size: 120, defect_count: 2, disposition: "Released" },
      { inspection_id: 502, sku: "PL-220", inspection_date: "2026-01-12", sample_size: 180, defect_count: 4, disposition: "Released" },
      { inspection_id: 503, sku: "AG-310", inspection_date: "2026-02-03", sample_size: 140, defect_count: 1, disposition: "Released" },
      { inspection_id: 504, sku: "MT-510", inspection_date: "2026-02-07", sample_size: 90, defect_count: 8, disposition: "Hold" },
      { inspection_id: 505, sku: "PL-330", inspection_date: "2026-03-16", sample_size: 110, defect_count: 6, disposition: "Hold" },
      { inspection_id: 506, sku: "CX-710", inspection_date: "2026-03-22", sample_size: 100, defect_count: 1, disposition: "Released" },
    ],
  },
  PurchaseOrders: {
    headers: ["po_id", "sku", "supplier_id", "order_date", "quantity_ordered", "unit_price", "status"],
    records: [
      { po_id: "PO-9001", sku: "SC-100", supplier_id: "S1", order_date: "2026-01-18", quantity_ordered: 40, unit_price: 1115, status: "Open" },
      { po_id: "PO-9002", sku: "MT-510", supplier_id: "S4", order_date: "2026-02-21", quantity_ordered: 30, unit_price: 2180, status: "Expedited" },
      { po_id: "PO-9003", sku: "PL-330", supplier_id: "S5", order_date: "2026-03-07", quantity_ordered: 60, unit_price: 445, status: "Open" },
      { po_id: "PO-9004", sku: "CX-710", supplier_id: "S6", order_date: "2026-03-28", quantity_ordered: 25, unit_price: 1260, status: "Received" },
    ],
  },
};

const people = {
  Departments: {
    headers: ["department_id", "department_name", "business_unit", "manager_name"],
    records: [
      { department_id: "D10", department_name: "Manufacturing Excellence", business_unit: "Operations", manager_name: "Nadia" },
      { department_id: "D20", department_name: "Commercial Analytics", business_unit: "Sales", manager_name: "Omar" },
      { department_id: "D30", department_name: "Supply Chain", business_unit: "Operations", manager_name: "Lina" },
      { department_id: "D40", department_name: "Digital", business_unit: "Technology", manager_name: "Ravi" },
    ],
  },
  Employees: {
    headers: ["employee_id", "employee_name", "department_id", "location", "hire_date", "role_level"],
    records: [
      { employee_id: "E001", employee_name: "Maya Chen", department_id: "D10", location: "Jubail", hire_date: "2023-04-11", role_level: "Senior" },
      { employee_id: "E002", employee_name: "Samir Khan", department_id: "D30", location: "Dammam", hire_date: "2024-02-01", role_level: "Associate" },
      { employee_id: "E003", employee_name: "Elena Rossi", department_id: "D20", location: "Rotterdam", hire_date: "2022-09-17", role_level: "Lead" },
      { employee_id: "E004", employee_name: "Aisha Noor", department_id: "D40", location: "Riyadh", hire_date: "2025-05-20", role_level: "Associate" },
      { employee_id: "E005", employee_name: "Jon Miller", department_id: "D30", location: "Houston", hire_date: "2021-12-03", role_level: "Senior" },
      { employee_id: "E006", employee_name: "Priya Menon", department_id: "D10", location: "Jubail", hire_date: "2024-08-22", role_level: "Associate" },
    ],
  },
  TrainingCompletions: {
    headers: ["employee_id", "course_name", "completion_date", "expires_on", "score"],
    records: [
      { employee_id: "E001", course_name: "Process Safety", completion_date: "2025-04-03", expires_on: "2026-04-03", score: 92 },
      { employee_id: "E002", course_name: "Process Safety", completion_date: "2024-10-12", expires_on: "2025-10-12", score: 81 },
      { employee_id: "E003", course_name: "Data Privacy", completion_date: "2025-09-09", expires_on: "2026-09-09", score: 95 },
      { employee_id: "E004", course_name: "Data Privacy", completion_date: "2025-02-15", expires_on: "2026-02-15", score: 78 },
      { employee_id: "E005", course_name: "Process Safety", completion_date: "2024-01-10", expires_on: "2025-01-10", score: 74 },
      { employee_id: "E006", course_name: "Process Safety", completion_date: "2026-01-18", expires_on: "2027-01-18", score: 88 },
    ],
  },
  PerformanceReviews: {
    headers: ["employee_id", "review_period", "performance_score", "engagement_score", "risk_flag"],
    records: [
      { employee_id: "E001", review_period: "2026-Q1", performance_score: 4.4, engagement_score: 83, risk_flag: "Low" },
      { employee_id: "E002", review_period: "2026-Q1", performance_score: 3.1, engagement_score: 62, risk_flag: "Medium" },
      { employee_id: "E003", review_period: "2026-Q1", performance_score: 4.7, engagement_score: 88, risk_flag: "Low" },
      { employee_id: "E004", review_period: "2026-Q1", performance_score: 3.5, engagement_score: 68, risk_flag: "Medium" },
      { employee_id: "E005", review_period: "2026-Q1", performance_score: 2.8, engagement_score: 55, risk_flag: "High" },
      { employee_id: "E006", review_period: "2026-Q1", performance_score: 3.9, engagement_score: 76, risk_flag: "Low" },
    ],
  },
  AbsenceLog: {
    headers: ["employee_id", "absence_date", "absence_type", "hours"],
    records: [
      { employee_id: "E002", absence_date: "2026-01-06", absence_type: "Sick", hours: 8 },
      { employee_id: "E002", absence_date: "2026-02-12", absence_type: "Sick", hours: 8 },
      { employee_id: "E004", absence_date: "2026-02-20", absence_type: "Personal", hours: 4 },
      { employee_id: "E005", absence_date: "2026-01-17", absence_type: "Sick", hours: 8 },
      { employee_id: "E005", absence_date: "2026-03-02", absence_type: "Sick", hours: 8 },
      { employee_id: "E005", absence_date: "2026-03-18", absence_type: "Personal", hours: 4 },
      { employee_id: "E006", absence_date: "2026-04-08", absence_type: "Sick", hours: 8 },
    ],
  },
};

const messy = {
  "Q2 Sales Export": {
    notes: ["Generated report: regional sales upload", "Columns begin on row 4 after report notes"],
    startCell: "A4",
    headers: ["Customer Name", "Region", "Order Date", "Revenue USD", "Gross Margin %", "Account Owner"],
    records: [
      { "Customer Name": "Blue Falcon", Region: "Europe", "Order Date": "2026-04-01", "Revenue USD": 18000, "Gross Margin %": 0.32, "Account Owner": "Elena" },
      { "Customer Name": "Desert Pearl", Region: "Middle East", "Order Date": "2026-04-09", "Revenue USD": 24500, "Gross Margin %": 0.28, "Account Owner": "Omar" },
      { "Customer Name": "Maple Works", Region: "North America", "Order Date": "2026-05-03", "Revenue USD": 15750, "Gross Margin %": 0.35, "Account Owner": "Avery" },
      { "Customer Name": "Sakura Labs", Region: "Asia", "Order Date": "2026-05-19", "Revenue USD": 31100, "Gross Margin %": 0.3, "Account Owner": "Kai" },
      { "Customer Name": "Rhine Parts", Region: "Europe", "Order Date": "2026-06-06", "Revenue USD": 22100, "Gross Margin %": 0.27, "Account Owner": "Elena" },
    ],
  },
  "Renewal Watchlist": {
    headers: ["account", "renewal_month", "contract_value", "health_score", "owner"],
    records: [
      { account: "Blue Falcon", renewal_month: "2026-07", contract_value: 84000, health_score: 78, owner: "Elena" },
      { account: "Desert Pearl", renewal_month: "2026-08", contract_value: 126000, health_score: 64, owner: "Omar" },
      { account: "Sakura Labs", renewal_month: "2026-08", contract_value: 91000, health_score: 82, owner: "Kai" },
      { account: "Maple Works", renewal_month: "2026-09", contract_value: 57000, health_score: 59, owner: "Avery" },
    ],
  },
};

const supportTicketsCsv = `ticket_id,created_date,customer_name,priority,status,product_area,resolution_hours
T-1001,2026-04-01,Blue Falcon,High,Closed,Portal,18
T-1002,2026-04-02,Desert Pearl,Critical,Open,Data Sync,42
T-1003,2026-04-05,Maple Works,Medium,Closed,Analytics,26
T-1004,2026-04-07,Sakura Labs,Low,Closed,Portal,9
T-1005,2026-04-11,Rhine Parts,High,Open,Data Sync,55
T-1006,2026-04-14,Blue Falcon,Medium,Closed,Analytics,22
`;

await fs.mkdir(outputDir, { recursive: true });
const files = [];
files.push(await saveWorkbook("qa_retail_operations.xlsx", retail));
files.push(await saveWorkbook("qa_manufacturing_quality.xlsx", manufacturing));
files.push(await saveWorkbook("qa_people_analytics.xlsx", people));
files.push(await saveWorkbook("qa_messy_sales_export.xlsx", messy));
const csvPath = path.join(outputDir, "qa_support_tickets.csv");
await fs.writeFile(csvPath, supportTicketsCsv, "utf8");
files.push(csvPath);

const manifest = {
  generated_at: new Date().toISOString(),
  files,
  expected_hints: {
    retail_regions: ["Asia", "Europe", "Middle East", "North America"],
    manufacturing_low_stock_skus: ["SC-100", "MT-510", "PL-330"],
    manufacturing_warehouses: ["Dammam Hub", "Jubail Complex", "Rotterdam Terminal", "Houston Depot"],
    people_overdue_training: ["Samir Khan", "Jon Miller", "Aisha Noor"],
    messy_highest_revenue_account: "Sakura Labs",
  },
};
await fs.writeFile(path.join(outputDir, "qa_manifest.json"), JSON.stringify(manifest, null, 2));

console.log(JSON.stringify(manifest, null, 2));
