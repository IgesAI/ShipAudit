const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Finding = {
  id: string;
  finding_type: string;
  verdict: string;
  confidence_class: string;
  status: string;
  severity: string;
  confidence: string;
  billed_amount: string;
  expected_amount: string | null;
  recoverable_amount: string;
  explanation: string;
  evidence: Record<string, unknown>;
  created_at: string;
};

export type Case = {
  id: string;
  finding_id: string;
  status: string;
  auto_dispute_eligible: boolean;
  dispute_deadline: string | null;
  title: string;
  summary: string;
  evidence_packet: Record<string, unknown>;
  evidence_document: string | null;
  reviewer_notes: string | null;
};

export type RejectedRow = {
  id: string;
  ingest_stage: string;
  row_index: number | null;
  row_payload: Record<string, unknown>;
  failure_reasons: string[];
  created_at: string;
};

export type RateCard = {
  id: string;
  carrier: string;
  account_number: string;
  name: string;
  effective_start: string;
  effective_end: string | null;
  source_file_hash: string;
};

export type Dispute = {
  id: string;
  case_id: string;
  carrier: string;
  status: string;
  submission_channel: string;
  external_reference: string | null;
};

export type Refund = {
  id: string;
  invoice_number: string;
  tracking_number: string;
  charge_type: string;
  expected_credit: string;
  posted_credit: string | null;
  status: string;
  credit_invoice_number: string | null;
};

export type InvoiceSummary = {
  id: string;
  carrier: string;
  invoice_number: string;
  invoice_date: string;
  account_number: string;
  currency: string;
  total_amount: string;
  status: string;
};

export type UploadResponse = {
  invoice_id: string | null;
  shipment_count: number;
  line_count: number;
  rejected_count: number;
  artifact_id: string | null;
};

export type DashboardSummary = {
  invoices: number;
  invoice_lines: number;
  findings_open: number;
  findings_total: number;
  cases_needing_review: number;
  disputes_submitted: number;
  rejected_rows: number;
  expected_recovery: string;
  posted_recovery: string;
  recovery_rate: string;
  verdict_breakdown: Array<{ verdict: string; count: number; recoverable: string }>;
  surcharge_mix: Array<{ type: string; count: number; recoverable: string }>;
  latest_findings: Finding[];
};

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export function fetchDashboard() {
  return api<DashboardSummary>("/api/dashboard");
}

export function fetchFindings() {
  return api<Finding[]>("/api/findings");
}

export function fetchCases() {
  return api<Case[]>("/api/cases");
}

export function fetchDisputes() {
  return api<Dispute[]>("/api/disputes");
}

export function fetchRefunds() {
  return api<Refund[]>("/api/refunds");
}

export function fetchRejectedRows() {
  return api<RejectedRow[]>("/api/rejected-rows");
}

export function fetchRateCards() {
  return api<RateCard[]>("/api/rate-cards");
}

export function fetchInvoices() {
  return api<InvoiceSummary[]>("/api/invoices");
}

async function uploadFile<T>(path: string, file: File): Promise<T> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${API_BASE}${path}`, { method: "POST", body });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      if (payload?.detail) {
        detail =
          typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
      }
    } catch {
      // keep status text
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export function uploadInvoiceFile(file: File) {
  return uploadFile<UploadResponse>("/api/ingest/invoices", file);
}

export function uploadManifestFile(file: File) {
  return uploadFile<UploadResponse>("/api/ingest/manifests", file);
}

export function uploadRateCardFile(file: File) {
  return uploadFile<RateCard>("/api/ingest/rate-cards", file);
}

export function seedCarrierRules() {
  return api<{ inserted: number }>("/api/rules/seed", { method: "POST" });
}

export function auditInvoice(invoiceId: string) {
  return api<Finding[]>(`/api/audit/invoices/${invoiceId}`, { method: "POST" });
}

export function buildCases() {
  return api<Case[]>("/api/cases/build", { method: "POST" });
}
