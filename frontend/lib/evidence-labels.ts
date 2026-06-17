const LABELS: Record<string, string> = {
  invoice_number: "Invoice number",
  invoice_date: "Invoice date",
  invoice_source_hash: "Invoice file",
  tracking_number: "Tracking number",
  charge_code: "Charge type",
  ship_date: "Ship date",
  duplicate_scope: "Duplicate found",
  prior_invoice_id: "Prior invoice",
  prior_invoice_line_id: "Prior charge line",
  missing_source: "Blocked because",
  rule_version_id: "Rule version",
  rule_source_uri: "Rule source",
  rule_source_hash: "Rule file",
  rate_card_name: "Rate card",
  rate_card_hash: "Rate card file",
  source_filename: "Uploaded file",
  source_sha256: "File fingerprint",
  row_index: "Row in file",
  format: "File format",
  shipment_id: "Manifest record",
  service_code: "Service",
  weight_lbs: "Manifest weight",
  number: "Invoice number",
  date: "Invoice date",
  carrier: "Carrier",
  account_number: "Account",
  source_file_hash: "Source file",
  id: "Record ID",
  amount: "Amount",
  description: "Description",
  charge_type: "Charge category",
  claim_amount: "Claim amount",
  verdict: "Verdict",
  confidence_class: "Confidence",
  dispute_deadline: "Dispute deadline",
  channel: "Submission channel",
  requires_human_approval: "Needs human approval",
  manifest_service_code: "Manifest service",
};

const CHARGE_NAMES: Record<string, string> = {
  FUEL: "Fuel surcharge",
  OTHER: "Other charge",
  BASE_RATE: "Base transportation",
  FRT: "Freight",
  RESIDENTIAL: "Residential delivery",
  DELIVERY_AREA: "Delivery area surcharge",
  DAS: "Delivery area surcharge",
  CONTRACT_DISCOUNT: "Contract discount",
  DUPLICATE_CHARGE: "Duplicate charge",
};

const FORMAT_NAMES: Record<string, string> = {
  ups_billing_csv: "UPS billing export",
  fedex_selectable_csv: "FedEx billing export",
  pdf_docling: "PDF invoice (OCR)",
  csv: "Canonical CSV",
};

const SCOPE_NAMES: Record<string, string> = {
  same_invoice: "Billed twice on this invoice",
  prior_invoice: "Billed on a prior invoice",
};

const MISSING_NAMES: Record<string, string> = {
  shipment_manifest: "No matching manifest uploaded",
  destination_address: "No destination address on file",
  carrier_zip_table: "Carrier ZIP table not loaded",
};

export function evidenceLabel(key: string): string {
  return LABELS[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function humanizeEvidenceValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return "";
  const text = String(value);
  if (key === "charge_code" || key === "charge_type") {
    return CHARGE_NAMES[text] ?? text.replace(/_/g, " ").toLowerCase();
  }
  if (key === "format") return FORMAT_NAMES[text] ?? text;
  if (key === "duplicate_scope") return SCOPE_NAMES[text] ?? text.replace(/_/g, " ");
  if (key === "missing_source") return MISSING_NAMES[text] ?? text.replace(/_/g, " ");
  if (key.endsWith("_amount") || key === "amount") {
    const num = Number(text);
    if (!Number.isNaN(num)) return `$${num.toFixed(2)}`;
  }
  return text;
}

export function formatEvidenceValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return "";
  return String(value);
}

export function isHashKey(key: string): boolean {
  return key.includes("hash") || key === "source_sha256";
}

export function shortenHash(value: string, head = 10, tail = 6): string {
  if (value.length <= head + tail + 1) return value;
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}

const VERDICT_NAMES: Record<string, string> = {
  DISCREPANCY: "Billing error",
  PASS: "Passed audit",
  NO_CLAIM: "No claim",
  FAIL_MISSING_SOURCE: "Missing source data",
  FAIL_RULE_GAP: "Rule not available",
  REJECTED: "Rejected",
};

const FINDING_NAMES: Record<string, string> = {
  DUPLICATE_CHARGE: "Duplicate charge",
  RATE_MISMATCH: "Rate mismatch",
  WEIGHT_MISMATCH: "Weight mismatch",
  ZONE_MISMATCH: "Zone mismatch",
  SURCHARGE_MISMATCH: "Surcharge mismatch",
  OTHER: "Other charge",
};

export function humanizeVerdict(value: string): string {
  return VERDICT_NAMES[value] ?? value.replace(/_/g, " ").toLowerCase();
}

export function humanizeFindingType(value: string): string {
  return FINDING_NAMES[value] ?? value.replace(/_/g, " ").toLowerCase();
}

export function shortenFilename(value: string, max = 42): string {
  if (value.length <= max) return value;
  const ext = value.includes(".") ? value.slice(value.lastIndexOf(".")) : "";
  const base = ext ? value.slice(0, value.lastIndexOf(".")) : value;
  const keep = max - ext.length - 1;
  return `${base.slice(0, keep)}…${ext}`;
}
