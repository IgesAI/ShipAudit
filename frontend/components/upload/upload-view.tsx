"use client";

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import {
  CheckCircle2,
  FileSpreadsheet,
  FileJson,
  FileText,
  Gavel,
  ListChecks,
  Loader2,
  PackageSearch,
  ShieldCheck,
  Trash2,
  Truck,
  UploadCloud,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  GlassCard,
  GlassCardContent,
  GlassCardDescription,
  GlassCardHeader,
  GlassCardTitle,
} from "@/components/ui/glass-card";
import {
  auditInvoice,
  buildCases,
  fetchInvoices,
  fetchRateCards,
  confirmPdfExtraction,
  deleteInvoice,
  seedCarrierRules,
  uploadCarrierExportFile,
  uploadInvoiceFile,
  uploadManifestFile,
  uploadPdfInvoiceFile,
  uploadRateCardFile,
  type CarrierHint,
  type InvoiceSummary,
  type PdfIngestResponse,
  type RateCard,
  type UploadResponse,
} from "@/lib/api";
import { money } from "@/lib/utils";

type Feedback = { kind: "success" | "error"; message: string };

function FeedbackLine({ feedback }: { feedback: Feedback | null }) {
  if (!feedback) return null;
  return (
    <p
      className={
        feedback.kind === "success"
          ? "mt-3 text-xs text-emerald-300"
          : "mt-3 text-xs text-red-300"
      }
    >
      {feedback.message}
    </p>
  );
}

function UploadCard({
  title,
  description,
  accept,
  icon: Icon,
  onUpload,
  hint,
}: {
  title: string;
  description: string;
  accept: string;
  icon: typeof UploadCloud;
  onUpload: (file: File) => Promise<string>;
  hint: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  async function handleFile(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setFeedback(null);
    try {
      const message = await onUpload(file);
      setFeedback({ kind: "success", message });
    } catch (err) {
      setFeedback({
        kind: "error",
        message: err instanceof Error ? err.message : "Upload failed",
      });
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <GlassCard className="upload-card flex flex-col">
      <GlassCardHeader>
        <div className="flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/30">
            <Icon className="h-5 w-5 text-primary" />
          </div>
          <div>
            <GlassCardTitle>{title}</GlassCardTitle>
            <GlassCardDescription>{description}</GlassCardDescription>
          </div>
        </div>
      </GlassCardHeader>
      <GlassCardContent className="mt-auto">
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          aria-label={`${title} file`}
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
        <Button onClick={() => inputRef.current?.click()} disabled={busy} className="w-full">
          {busy ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <UploadCloud className="mr-2 h-4 w-4" />
          )}
          {busy ? "Uploading..." : `Choose file (${hint})`}
        </Button>
        <FeedbackLine feedback={feedback} />
      </GlassCardContent>
    </GlassCard>
  );
}

function CarrierExportCard({ onUpload }: { onUpload: (file: File, carrier?: CarrierHint) => Promise<string> }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [carrier, setCarrier] = useState<"AUTO" | CarrierHint>("AUTO");
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  async function handleFile(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setFeedback(null);
    try {
      const message = await onUpload(file, carrier === "AUTO" ? undefined : carrier);
      setFeedback({ kind: "success", message });
    } catch (err) {
      setFeedback({ kind: "error", message: err instanceof Error ? err.message : "Upload failed" });
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <GlassCard className="upload-card flex flex-col">
      <GlassCardHeader>
        <div className="flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/30">
            <Truck className="h-5 w-5 text-primary" />
          </div>
          <div>
            <GlassCardTitle>Step 3 — Carrier billing export</GlassCardTitle>
            <GlassCardDescription>
              Upload the file straight from UPS Billing Center or FedEx Billing Online (CSV). Many
              invoices and shipments are split apart automatically; charges we do not audit are kept
              but never disputed.
            </GlassCardDescription>
          </div>
        </div>
      </GlassCardHeader>
      <GlassCardContent className="mt-auto space-y-3">
        <div className="flex flex-wrap gap-2">
          {(["AUTO", "UPS", "FEDEX"] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setCarrier(value)}
              className={
                carrier === value
                  ? "rounded-lg bg-primary/20 px-3 py-1.5 text-xs font-medium text-primary ring-1 ring-primary/40"
                  : "rounded-lg bg-white/[0.03] px-3 py-1.5 text-xs text-muted-foreground ring-1 ring-white/10 hover:bg-white/[0.06]"
              }
            >
              {value === "AUTO" ? "Auto-detect" : value}
            </button>
          ))}
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          aria-label="Carrier billing export file"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
        <Button onClick={() => inputRef.current?.click()} disabled={busy} className="w-full">
          {busy ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <UploadCloud className="mr-2 h-4 w-4" />
          )}
          {busy ? "Mapping & ingesting..." : "Choose carrier export (.csv)"}
        </Button>
        <FeedbackLine feedback={feedback} />
      </GlassCardContent>
    </GlassCard>
  );
}

function PdfInvoiceCard({ onConfirmed }: { onConfirmed: () => Promise<void> }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState<PdfIngestResponse | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  async function handleFile(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setFeedback(null);
    setPending(null);
    try {
      const result = await uploadPdfInvoiceFile(file);
      if (result.rejected || result.candidate_rows.length === 0) {
        setFeedback({
          kind: "error",
          message:
            result.reason ??
            "Could not map charge lines from this PDF. Use the carrier CSV export (Step 3) instead.",
        });
      } else {
        setPending(result);
        setFeedback({
          kind: "success",
          message: `Extracted ${result.candidate_rows.length} charge line(s) at ${Math.round(
            (result.ocr_confidence ?? 0) * 100,
          )}% confidence. Review below, then confirm.`,
        });
      }
    } catch (err) {
      setFeedback({ kind: "error", message: err instanceof Error ? err.message : "Upload failed" });
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function handleConfirm() {
    if (!pending) return;
    setConfirming(true);
    try {
      const result = await confirmPdfExtraction(pending.artifact_id);
      await onConfirmed();
      setPending(null);
      setFeedback({
        kind: result.invoice_count > 0 ? "success" : "error",
        message:
          result.invoice_count > 0
            ? `Confirmed: ingested ${result.invoice_count} invoice(s), ${result.line_count} lines. Run the audit below.`
            : `Nothing ingested. ${result.rejected_count} row(s) rejected — see the rejected-rows panel.`,
      });
    } catch (err) {
      setFeedback({ kind: "error", message: err instanceof Error ? err.message : "Confirm failed" });
    } finally {
      setConfirming(false);
    }
  }

  const previewKeys = ["invoice_number", "tracking_number", "charge_code", "amount"];

  return (
    <GlassCard className="upload-card">
      <GlassCardHeader>
        <div className="flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/30">
            <FileText className="h-5 w-5 text-primary" />
          </div>
          <div>
            <GlassCardTitle>PDF invoice (OCR + confirm)</GlassCardTitle>
            <GlassCardDescription>
              Drop a carrier PDF. We extract it with Docling, reject anything below the OCR
              confidence gate, and show what we read for you to confirm before it is ever audited.
            </GlassCardDescription>
          </div>
        </div>
      </GlassCardHeader>
      <GlassCardContent className="space-y-4">
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,application/pdf"
          className="hidden"
          aria-label="PDF invoice file"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
        <Button onClick={() => inputRef.current?.click()} disabled={busy || confirming}>
          {busy ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <UploadCloud className="mr-2 h-4 w-4" />
          )}
          {busy ? "Extracting (may take up to 60s)..." : "Choose PDF invoice"}
        </Button>
        <FeedbackLine feedback={feedback} />

        {pending ? (
          <div className="space-y-3 rounded-lg border border-primary/20 bg-primary/[0.04] p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-wide text-muted-foreground">
                Review extracted lines
              </span>
              <Button onClick={handleConfirm} disabled={confirming} className="h-8 px-3">
                {confirming ? (
                  <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <CheckCircle2 className="mr-2 h-3.5 w-3.5" />
                )}
                Confirm & ingest
              </Button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="uppercase text-muted-foreground">
                  <tr className="border-b border-white/10">
                    {previewKeys.map((key) => (
                      <th key={key} className="py-2 pr-4">
                        {key.replace("_", " ")}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pending.candidate_rows.slice(0, 12).map((row, idx) => (
                    <tr key={idx} className="border-b border-white/5 last:border-b-0">
                      {previewKeys.map((key) => (
                        <td key={key} className="py-1.5 pr-4">
                          {row[key] ?? ""}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {pending.candidate_rows.length > 12 ? (
                <p className="mt-2 text-xs text-muted-foreground">
                  +{pending.candidate_rows.length - 12} more line(s)
                </p>
              ) : null}
            </div>
          </div>
        ) : null}
      </GlassCardContent>
    </GlassCard>
  );
}

export function UploadView() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [invoices, setInvoices] = useState<InvoiceSummary[]>([]);
  const [rateCards, setRateCards] = useState<RateCard[]>([]);
  const [auditing, setAuditing] = useState<string | null>(null);
  const [auditFeedback, setAuditFeedback] = useState<Feedback | null>(null);
  const [rulesFeedback, setRulesFeedback] = useState<Feedback | null>(null);
  const [seedingRules, setSeedingRules] = useState(false);
  const [buildingCases, setBuildingCases] = useState(false);
  const [invoiceCarrierFilter, setInvoiceCarrierFilter] = useState<"" | "UPS" | "FEDEX" | "USPS">("");
  const [deletingInvoiceId, setDeletingInvoiceId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [invoiceList, cardList] = await Promise.all([
      fetchInvoices(invoiceCarrierFilter || undefined),
      fetchRateCards(),
    ]);
    setInvoices(invoiceList);
    setRateCards(cardList);
    setLoadError(null);
  }, [invoiceCarrierFilter]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchInvoices(invoiceCarrierFilter || undefined), fetchRateCards()])
      .then(([invoiceList, cardList]) => {
        if (!cancelled) {
          setInvoices(invoiceList);
          setRateCards(cardList);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "Unable to reach the API");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [invoiceCarrierFilter]);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.from(".upload-card", {
          y: 16,
          duration: 0.4,
          stagger: 0.07,
          ease: "power2.out",
          clearProps: "transform",
        });
      });
      return () => mm.revert();
    },
    { scope: containerRef },
  );

  async function handleSeedRules() {
    setSeedingRules(true);
    setRulesFeedback(null);
    try {
      const result = await seedCarrierRules();
      setRulesFeedback({
        kind: "success",
        message:
          result.inserted > 0
            ? `Loaded ${result.inserted} carrier rule tables.`
            : "Carrier rules already loaded.",
      });
    } catch (err) {
      setRulesFeedback({
        kind: "error",
        message: err instanceof Error ? err.message : "Failed to seed rules",
      });
    } finally {
      setSeedingRules(false);
    }
  }

  async function handleAudit(invoiceId: string, invoiceNumber: string) {
    setAuditing(invoiceId);
    setAuditFeedback(null);
    try {
      const findings = await auditInvoice(invoiceId);
      setAuditFeedback({
        kind: "success",
        message: `Audited ${invoiceNumber}: ${findings.length} findings. Build cases to create disputes from proven discrepancies.`,
      });
      await refresh();
    } catch (err) {
      setAuditFeedback({
        kind: "error",
        message: err instanceof Error ? err.message : "Audit failed",
      });
    } finally {
      setAuditing(null);
    }
  }

  async function handleDeleteInvoice(invoiceId: string, invoiceNumber: string) {
    if (
      !window.confirm(
        `Delete invoice ${invoiceNumber} and all its charge lines, findings, and dispute cases? This cannot be undone.`,
      )
    ) {
      return;
    }
    setDeletingInvoiceId(invoiceId);
    setAuditFeedback(null);
    try {
      const removed = await deleteInvoice(invoiceId);
      setAuditFeedback({
        kind: "success",
        message: `Removed ${invoiceNumber} (${removed.findings ?? 0} findings, ${removed.cases ?? 0} cases cleared).`,
      });
      await refresh();
    } catch (err) {
      setAuditFeedback({
        kind: "error",
        message: err instanceof Error ? err.message : "Delete failed",
      });
    } finally {
      setDeletingInvoiceId(null);
    }
  }

  async function handleBuildCases() {
    setBuildingCases(true);
    setAuditFeedback(null);
    try {
      const cases = await buildCases();
      setAuditFeedback({
        kind: "success",
        message: `Built ${cases.length} dispute case${cases.length === 1 ? "" : "s"} from proven discrepancies.`,
      });
    } catch (err) {
      setAuditFeedback({
        kind: "error",
        message: err instanceof Error ? err.message : "Case build failed",
      });
    } finally {
      setBuildingCases(false);
    }
  }

  return (
    <div ref={containerRef} className="flex flex-col gap-6">
      {loadError ? (
        <GlassCard className="border-red-500/40 bg-red-500/10">
          <GlassCardContent className="pt-6 text-sm text-red-200">
            Cannot reach the API ({loadError}). Start the backend with{" "}
            <code className="rounded bg-black/30 px-1">docker compose up</code>.
          </GlassCardContent>
        </GlassCard>
      ) : null}
      <GlassCard variant="yellow" className="upload-card p-6 md:p-8">
        <div className="flex items-start gap-4">
          <UploadCloud className="mt-1 h-8 w-8 text-primary" />
          <div>
            <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">Upload & Audit</h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
              Bring your real billing data. The pipeline is fail-closed: load carrier rules and your
              contract rate card first, then upload invoice exports and run the audit. Anything the
              system cannot verify is rejected or marked FAIL — never guessed.
            </p>
          </div>
        </div>
      </GlassCard>

      <GlassCard className="upload-card">
        <GlassCardHeader>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" />
            <GlassCardTitle>Step 1 — Carrier rule tables</GlassCardTitle>
          </div>
          <GlassCardDescription>
            Area-surcharge ZIP lists, fuel schedules, dim divisors, and dispute policies. Required
            before any audit can produce verdicts. Loads the bundled FedEx / UPS / USPS rule pack.
          </GlassCardDescription>
        </GlassCardHeader>
        <GlassCardContent>
          <Button onClick={handleSeedRules} disabled={seedingRules}>
            {seedingRules ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <ListChecks className="mr-2 h-4 w-4" />
            )}
            Load carrier rules
          </Button>
          <FeedbackLine feedback={rulesFeedback} />
        </GlassCardContent>
      </GlassCard>

      <section className="grid gap-6 md:grid-cols-2">
        <UploadCard
          title="Step 2 — Rate card"
          description="Your negotiated contract: discounts, minimums, accessorial schedule. JSON format. Rate audits hard-fail without one."
          accept=".json,application/json"
          icon={FileJson}
          hint=".json"
          onUpload={async (file) => {
            const card = await uploadRateCardFile(file);
            await refresh();
            return `Compiled rate card "${card.name}" for ${card.carrier} (effective ${card.effective_start}).`;
          }}
        />
        <CarrierExportCard
          onUpload={async (file, carrier) => {
            const result: UploadResponse = await uploadCarrierExportFile(file, carrier);
            await refresh();
            if (result.invoice_count === 0) {
              return `No invoices ingested. ${result.rejected_count} row(s) rejected — check the dashboard rejected-rows panel for details (common causes: wrong file type, or this invoice was already uploaded).`;
            }
            const rejected =
              result.rejected_count > 0
                ? ` ${result.rejected_count} rejected (see dashboard rejected-rows panel).`
                : "";
            return `Ingested ${result.invoice_count} invoice${result.invoice_count === 1 ? "" : "s"} (${result.line_count} charge lines).${rejected} Run the audit below.`;
          }}
        />
        <UploadCard
          title="Optional — Shipment manifest"
          description="Your outbound shipment records (CSV). Enables dim-weight and service-level cross checks against what you actually tendered."
          accept=".csv,text/csv"
          icon={PackageSearch}
          hint=".csv"
          onUpload={async (file) => {
            const result: UploadResponse = await uploadManifestFile(file);
            const rejected =
              result.rejected_count > 0 ? ` ${result.rejected_count} rejected.` : "";
            return `Ingested ${result.shipment_count} shipments.${rejected}`;
          }}
        />
        <UploadCard
          title="Advanced — canonical CSV"
          description="One invoice per file in ShipAudit's exact column schema (see Docs). For power users and integrations; carrier exports above are mapped into this same schema."
          accept=".csv,text/csv"
          icon={FileSpreadsheet}
          hint=".csv"
          onUpload={async (file) => {
            const result: UploadResponse = await uploadInvoiceFile(file);
            await refresh();
            const rejected =
              result.rejected_count > 0
                ? ` ${result.rejected_count} rejected (see dashboard rejected-rows panel).`
                : "";
            return `Ingested ${result.line_count} lines.${rejected} Run the audit below.`;
          }}
        />
      </section>

      <PdfInvoiceCard onConfirmed={refresh} />

      <GlassCard className="upload-card">
        <GlassCardHeader>
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <Gavel className="h-4 w-4 text-primary" />
                <GlassCardTitle>Step 4 — Run audits & build cases</GlassCardTitle>
              </div>
              <GlassCardDescription>
                Audit each ingested invoice, then build dispute cases from proven discrepancies.
              </GlassCardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={handleBuildCases} disabled={buildingCases}>
                {buildingCases ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Gavel className="mr-2 h-4 w-4" />
                )}
                Build dispute cases
              </Button>
              <Link
                href="/"
                className="inline-flex h-10 items-center justify-center rounded-lg border border-white/10 bg-white/[0.03] px-4 text-sm font-medium text-foreground transition hover:bg-white/[0.06]"
              >
                Open dashboard
              </Link>
            </div>
          </div>
        </GlassCardHeader>
        <GlassCardContent>
          <div className="mb-4 flex flex-wrap gap-2">
            {(["", "UPS", "FEDEX", "USPS"] as const).map((value) => (
              <button
                key={value || "all"}
                type="button"
                onClick={() => setInvoiceCarrierFilter(value)}
                className={
                  invoiceCarrierFilter === value
                    ? "rounded-lg bg-primary/20 px-3 py-1.5 text-xs font-medium text-primary ring-1 ring-primary/40"
                    : "rounded-lg bg-white/[0.03] px-3 py-1.5 text-xs text-muted-foreground ring-1 ring-white/10 hover:bg-white/[0.06]"
                }
              >
                {value || "All carriers"}
              </button>
            ))}
          </div>
          {invoices.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-muted-foreground">
                  <tr className="border-b border-white/10">
                    <th className="py-3">Invoice</th>
                    <th>Carrier</th>
                    <th>Date</th>
                    <th>Total</th>
                    <th>Status</th>
                    <th className="text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((invoice) => (
                    <tr key={invoice.id} className="border-b border-white/5 last:border-b-0">
                      <td className="py-3 font-medium">{invoice.invoice_number}</td>
                      <td>{invoice.carrier}</td>
                      <td className="text-xs text-muted-foreground">{invoice.invoice_date}</td>
                      <td>{money(invoice.total_amount)}</td>
                      <td>
                        <Badge variant="secondary">{invoice.status}</Badge>
                      </td>
                      <td className="py-2 text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            className="h-8 px-3"
                          disabled={deletingInvoiceId !== null}
                          onClick={() => handleAudit(invoice.id, invoice.invoice_number)}
                          >
                            {auditing === invoice.id ? (
                              <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <CheckCircle2 className="mr-2 h-3.5 w-3.5" />
                            )}
                            Run audit
                          </Button>
                          <Button
                            variant="ghost"
                            className="h-8 px-2 text-red-300 hover:bg-red-500/10 hover:text-red-200"
                            disabled={deletingInvoiceId !== null}
                            onClick={() => handleDeleteInvoice(invoice.id, invoice.invoice_number)}
                          >
                            {deletingInvoiceId === invoice.id ? (
                              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                            )}
                            Delete
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No invoices ingested yet. Upload a carrier billing export in Step 3 above.
            </p>
          )}
          <FeedbackLine feedback={auditFeedback} />
        </GlassCardContent>
      </GlassCard>

      <GlassCard className="upload-card">
        <GlassCardHeader>
          <GlassCardTitle>Compiled rate cards</GlassCardTitle>
          <GlassCardDescription>
            Effective-dated contract terms currently available to the audit engine.
          </GlassCardDescription>
        </GlassCardHeader>
        <GlassCardContent className="space-y-3">
          {rateCards.map((card) => (
            <div
              key={card.id}
              className="flex flex-col gap-1 rounded-lg border border-white/10 bg-white/[0.03] p-3 md:flex-row md:items-center md:justify-between"
            >
              <div>
                <div className="text-sm font-medium">{card.name}</div>
                <div className="text-xs text-muted-foreground">
                  {card.carrier} · account {card.account_number} · hash{" "}
                  {card.source_file_hash.slice(0, 12)}…
                </div>
              </div>
              <Badge>
                {card.effective_start} → {card.effective_end ?? "open"}
              </Badge>
            </div>
          ))}
          {!rateCards.length ? (
            <p className="text-sm text-muted-foreground">
              No rate cards compiled. Without one, rate and discount checks return FAIL (missing
              source).
            </p>
          ) : null}
        </GlassCardContent>
      </GlassCard>
    </div>
  );
}
