"use client";

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import {
  CheckCircle2,
  FileSpreadsheet,
  FileJson,
  Gavel,
  ListChecks,
  Loader2,
  PackageSearch,
  ShieldCheck,
  UploadCloud,
} from "lucide-react";
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
  seedCarrierRules,
  uploadInvoiceFile,
  uploadManifestFile,
  uploadRateCardFile,
  type InvoiceSummary,
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

export function UploadView() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [invoices, setInvoices] = useState<InvoiceSummary[]>([]);
  const [rateCards, setRateCards] = useState<RateCard[]>([]);
  const [auditing, setAuditing] = useState<string | null>(null);
  const [auditFeedback, setAuditFeedback] = useState<Feedback | null>(null);
  const [rulesFeedback, setRulesFeedback] = useState<Feedback | null>(null);
  const [seedingRules, setSeedingRules] = useState(false);
  const [buildingCases, setBuildingCases] = useState(false);

  const refresh = useCallback(async () => {
    const [invoiceList, cardList] = await Promise.all([fetchInvoices(), fetchRateCards()]);
    setInvoices(invoiceList);
    setRateCards(cardList);
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchInvoices(), fetchRateCards()])
      .then(([invoiceList, cardList]) => {
        if (!cancelled) {
          setInvoices(invoiceList);
          setRateCards(cardList);
        }
      })
      .catch(() => {
        // backend offline; cards will show empty states
      });
    return () => {
      cancelled = true;
    };
  }, []);

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

  async function handleBuildCases() {
    setBuildingCases(true);
    setAuditFeedback(null);
    try {
      const cases = await buildCases();
      setAuditFeedback({
        kind: "success",
        message: `Built ${cases.length} dispute case${cases.length === 1 ? "" : "s"} from proven discrepancies. View them on the dashboard.`,
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

      <section className="grid gap-6 xl:grid-cols-3">
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
        <UploadCard
          title="Step 3 — Invoice CSV"
          description="Carrier billing export (UPS Billing Center / FedEx Billing Online CSV). Every row is validated or rejected with explicit reasons."
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
      </section>

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
            <Button variant="secondary" onClick={handleBuildCases} disabled={buildingCases}>
              {buildingCases ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Gavel className="mr-2 h-4 w-4" />
              )}
              Build dispute cases
            </Button>
          </div>
        </GlassCardHeader>
        <GlassCardContent>
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
                    <th className="text-right">Audit</th>
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
                        <Button
                          variant="ghost"
                          className="h-8 px-3"
                          disabled={auditing !== null}
                          onClick={() => handleAudit(invoice.id, invoice.invoice_number)}
                        >
                          {auditing === invoice.id ? (
                            <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <CheckCircle2 className="mr-2 h-3.5 w-3.5" />
                          )}
                          Run audit
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No invoices ingested yet. Upload an invoice CSV above.
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
