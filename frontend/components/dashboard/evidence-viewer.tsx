"use client";

import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  GlassCard,
  GlassCardContent,
  GlassCardDescription,
  GlassCardHeader,
  GlassCardTitle,
} from "@/components/ui/glass-card";
import type { Case, Finding } from "@/lib/api";
import {
  humanizeEvidenceValue,
  humanizeFindingType,
  humanizeVerdict,
  shortenFilename,
  shortenHash,
} from "@/lib/evidence-labels";
import { money } from "@/lib/utils";

export type EvidenceSelection = { kind: "finding"; finding: Finding } | { kind: "case"; item: Case };

type EvidenceViewerProps = {
  selection: EvidenceSelection;
  onClose: () => void;
};

export function EvidenceViewer({ selection, onClose }: EvidenceViewerProps) {
  const title =
    selection.kind === "finding"
      ? humanizeFindingType(selection.finding.finding_type)
      : "Dispute packet";

  return (
    <GlassCard className="dash-panel">
      <GlassCardHeader>
        <div className="flex items-center justify-between gap-4">
          <div>
            <GlassCardTitle>{title}</GlassCardTitle>
            <GlassCardDescription>
              Plain-language audit support — every amount and source document is traceable.
            </GlassCardDescription>
          </div>
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      </GlassCardHeader>
      <GlassCardContent>
        {selection.kind === "finding" ? (
          <FindingEvidence finding={selection.finding} />
        ) : (
          <CaseEvidence item={selection.item} />
        )}
      </GlassCardContent>
    </GlassCard>
  );
}

function FindingEvidence({ finding }: { finding: Finding }) {
  const evidence = finding.evidence ?? {};
  const provenance =
    evidence.line_provenance && typeof evidence.line_provenance === "object"
      ? (evidence.line_provenance as Record<string, unknown>)
      : null;

  const detailRows: Array<{ label: string; value: ReactNode }> = [];
  if (evidence.duplicate_scope) {
    detailRows.push({
      label: "Duplicate found",
      value: humanizeEvidenceValue("duplicate_scope", evidence.duplicate_scope),
    });
  }
  if (evidence.missing_source) {
    detailRows.push({
      label: "Blocked because",
      value: humanizeEvidenceValue("missing_source", evidence.missing_source),
    });
  }

  return (
    <div className="space-y-6">
      <FindingSummary finding={finding} />

      <EvidenceSection title="Shipment & invoice">
        <FactTable
          rows={[
            { label: "Invoice number", value: String(evidence.invoice_number ?? "—") },
            { label: "Invoice date", value: String(evidence.invoice_date ?? "—") },
            { label: "Tracking number", value: String(evidence.tracking_number ?? "—") },
            {
              label: "Charge",
              value: humanizeEvidenceValue("charge_code", evidence.charge_code) || "—",
            },
            { label: "Ship date", value: String(evidence.ship_date ?? "—") },
          ]}
        />
      </EvidenceSection>

      {provenance ? (
        <EvidenceSection title="Where this line came from">
          <FactTable
            rows={[
              {
                label: "Uploaded file",
                value: provenance.source_filename
                  ? shortenFilename(String(provenance.source_filename))
                  : "—",
              },
              {
                label: "File fingerprint",
                value: hashValue(String(provenance.source_sha256 ?? "")),
              },
              {
                label: "Row in file",
                value:
                  provenance.row_index !== undefined && provenance.row_index !== null
                    ? `Row ${Number(provenance.row_index) + 1}`
                    : "—",
              },
              {
                label: "File format",
                value: humanizeEvidenceValue("format", provenance.format) || "—",
              },
            ]}
          />
        </EvidenceSection>
      ) : null}

      {detailRows.length ? (
        <EvidenceSection title="Why the audit stopped or flagged this">
          <FactTable rows={detailRows} />
        </EvidenceSection>
      ) : null}
    </div>
  );
}

function CaseEvidence({ item }: { item: Case }) {
  const packet = item.evidence_packet ?? {};
  const invoice =
    packet.invoice && typeof packet.invoice === "object"
      ? (packet.invoice as Record<string, unknown>)
      : null;
  const line =
    packet.line && typeof packet.line === "object" ? (packet.line as Record<string, unknown>) : null;
  const lineProvenance =
    line?.provenance && typeof line.provenance === "object"
      ? (line.provenance as Record<string, unknown>)
      : null;

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-5">
        <p className="text-base font-medium leading-snug">{item.title}</p>
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{item.summary}</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Badge>{String(packet.verdict ?? "DISCREPANCY").replace(/_/g, " ")}</Badge>
          <Badge variant="secondary">{String(packet.confidence_class ?? "n/a")}</Badge>
          {packet.claim_amount ? (
            <Badge variant="warning">Claim {money(String(packet.claim_amount))}</Badge>
          ) : null}
        </div>
      </div>

      {invoice ? (
        <EvidenceSection title="Invoice">
          <FactTable
            rows={[
              { label: "Invoice number", value: String(invoice.number ?? "—") },
              { label: "Invoice date", value: String(invoice.date ?? "—") },
              { label: "Carrier", value: String(invoice.carrier ?? "—") },
              { label: "Account", value: String(invoice.account_number ?? "—") },
              {
                label: "Source file",
                value: hashValue(String(invoice.source_file_hash ?? "")),
              },
            ]}
          />
        </EvidenceSection>
      ) : null}

      {line ? (
        <EvidenceSection title="Charge in dispute">
          <FactTable
            rows={[
              { label: "Tracking number", value: String(line.tracking_number ?? "—") },
              { label: "Service", value: String(line.service_code ?? "—") },
              { label: "Ship date", value: String(line.ship_date ?? "—") },
              {
                label: "Charge",
                value: humanizeEvidenceValue("charge_type", line.charge_type) || "—",
              },
              { label: "Description", value: String(line.description ?? line.charge_code ?? "—") },
              {
                label: "Billed amount",
                value: line.amount ? money(String(line.amount)) : "—",
              },
            ]}
          />
        </EvidenceSection>
      ) : null}

      {lineProvenance ? (
        <EvidenceSection title="Source document">
          <FactTable
            rows={[
              {
                label: "Uploaded file",
                value: lineProvenance.source_filename
                  ? shortenFilename(String(lineProvenance.source_filename))
                  : "—",
              },
              {
                label: "File fingerprint",
                value: hashValue(String(lineProvenance.source_sha256 ?? "")),
              },
              {
                label: "Row in file",
                value:
                  lineProvenance.row_index !== undefined && lineProvenance.row_index !== null
                    ? `Row ${Number(lineProvenance.row_index) + 1}`
                    : "—",
              },
            ]}
          />
        </EvidenceSection>
      ) : null}

      {item.evidence_document ? (
        <EvidenceSection title="Carrier dispute letter (draft)">
          <DisputeLetter text={item.evidence_document} />
        </EvidenceSection>
      ) : null}
    </div>
  );
}

function DisputeLetter({ text }: { text: string }) {
  const normalized = text.replace(/^## /m, "").trim();
  const sections = normalized.split(/^### /m).filter(Boolean);
  if (!sections.length) {
    return <p className="text-sm leading-relaxed text-muted-foreground">{normalized}</p>;
  }

  return (
    <div className="space-y-5">
      {sections.map((block) => {
        const [titleLine, ...bodyLines] = block.split("\n");
        const body = bodyLines.join("\n").trim();
        const rows = parseMarkdownTable(body);
        if (rows.length) {
          return (
            <div key={titleLine}>
              <h5 className="mb-2 text-sm font-medium text-foreground">{titleLine.trim()}</h5>
              <FactTable rows={rows} />
            </div>
          );
        }
        if (body.startsWith(">")) {
          return (
            <div key={titleLine}>
              <h5 className="mb-2 text-sm font-medium text-foreground">{titleLine.trim()}</h5>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {body.replace(/^>\s?/m, "")}
              </p>
            </div>
          );
        }
        return (
          <div key={titleLine}>
            <h5 className="mb-2 text-sm font-medium text-foreground">{titleLine.trim()}</h5>
            <p className="text-sm leading-relaxed text-muted-foreground">{body}</p>
          </div>
        );
      })}
    </div>
  );
}

function parseMarkdownTable(body: string): Array<{ label: string; value: ReactNode }> {
  const lines = body.split("\n").filter((line) => line.startsWith("|") && !line.includes("---"));
  return lines
    .map((line) => {
      const cells = line
        .split("|")
        .map((c) => c.trim())
        .filter(Boolean)
        .map((c) => c.replace(/`/g, ""));
      if (cells.length < 2) return null;
      const label = cells[0];
      const value = cells.slice(1).join(" · ");
      if (label.toLowerCase() === "field" || label === "") return null;
      return { label, value: value || "—" };
    })
    .filter((row): row is { label: string; value: string } => row !== null);
}

function FindingSummary({ finding }: { finding: Finding }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-base font-medium">{humanizeFindingType(finding.finding_type)}</span>
        <Badge
          variant={
            finding.verdict === "DISCREPANCY"
              ? "destructive"
              : finding.verdict === "PASS" || finding.verdict === "NO_CLAIM"
                ? "success"
                : "secondary"
          }
        >
          {humanizeVerdict(finding.verdict)}
        </Badge>
        <Badge variant="secondary">{finding.confidence_class}</Badge>
      </div>
      <p className="mt-4 text-sm leading-relaxed text-foreground/90">{finding.explanation}</p>
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <AmountTile label="Billed" value={money(finding.billed_amount)} />
        <AmountTile
          label="Expected"
          value={finding.expected_amount != null ? money(finding.expected_amount) : "—"}
        />
        <AmountTile label="Claim" value={money(finding.recoverable_amount)} highlight />
      </div>
    </div>
  );
}

function AmountTile({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-black/15 px-4 py-3">
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={`mt-1 text-xl font-semibold ${highlight ? "text-primary" : ""}`}>{value}</div>
    </div>
  );
}

function EvidenceSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h4 className="mb-3 text-sm font-semibold text-foreground">{title}</h4>
      {children}
    </section>
  );
}

function FactTable({ rows }: { rows: Array<{ label: string; value: ReactNode }> }) {
  return (
    <dl className="evidence-facts divide-y divide-white/8 rounded-lg border border-white/10 bg-white/[0.02]">
      {rows.map(({ label, value }) => (
        <div key={label} className="grid gap-1 px-4 py-3 sm:grid-cols-[9rem_1fr] sm:gap-4">
          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
          <dd className="text-sm leading-relaxed text-foreground">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function hashValue(value: string): ReactNode {
  if (!value || value === "n/a") return "—";
  return (
    <span className="text-muted-foreground" title={value}>
      {shortenHash(value)}
    </span>
  );
}
