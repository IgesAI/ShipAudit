"use client";

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, CheckCircle2, RefreshCw, ShieldX, Trash2, UploadCloud } from "lucide-react";

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
  Case,
  Dispute,
  clearRejectedRows,
  deleteInvoice,
  decideCase,
  fetchCases,
  fetchDashboard,
  fetchDisputes,
  fetchFindings,
  fetchInvoices,
  fetchRefunds,
  fetchRejectedRows,
  submitReadyDisputes,
  Finding,
  type FindingFilters,
  InvoiceSummary,
  Refund,
  RejectedRow,
  type DashboardSummary,
} from "@/lib/api";
import { cn, money } from "@/lib/utils";
import { EvidenceViewer, type EvidenceSelection } from "@/components/dashboard/evidence-viewer";

async function fetchAllData(findingFilters?: FindingFilters) {
  const [summary, findings, cases, disputes, refunds, rejectedRows, invoices] = await Promise.all([
    fetchDashboard(),
    fetchFindings(findingFilters),
    fetchCases(),
    fetchDisputes(),
    fetchRefunds(),
    fetchRejectedRows(),
    fetchInvoices(),
  ]);
  return { summary, findings, cases, disputes, refunds, rejectedRows, invoices };
}

export function DashboardView() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [cases, setCases] = useState<Case[]>([]);
  const [disputes, setDisputes] = useState<Dispute[]>([]);
  const [refunds, setRefunds] = useState<Refund[]>([]);
  const [rejectedRows, setRejectedRows] = useState<RejectedRow[]>([]);
  const [invoices, setInvoices] = useState<InvoiceSummary[]>([]);
  const [findingFilters, setFindingFilters] = useState<FindingFilters>({});
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceSelection | null>(null);
  const [loading, setLoading] = useState(true);
  const [clearingRejected, setClearingRejected] = useState(false);
  const [submittingDisputes, setSubmittingDisputes] = useState(false);
  const [decidingCaseId, setDecidingCaseId] = useState<string | null>(null);
  const [deletingInvoiceId, setDeletingInvoiceId] = useState<string | null>(null);
  const [workflowMessage, setWorkflowMessage] = useState<string | null>(null);
  const evidenceRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  const applyData = useCallback((data: Awaited<ReturnType<typeof fetchAllData>>) => {
    setSummary(data.summary);
    setFindings(data.findings);
    setCases(data.cases);
    setDisputes(data.disputes);
    setRefunds(data.refunds);
    setRejectedRows(data.rejectedRows);
    setInvoices(data.invoices);
  }, []);

  const refresh = useCallback(
    async (filters?: FindingFilters) => {
      setLoading(true);
      setError(null);
      try {
        applyData(await fetchAllData(filters ?? findingFilters));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load dashboard");
      } finally {
        setLoading(false);
      }
    },
    [applyData, findingFilters],
  );

  useEffect(() => {
    let cancelled = false;
    fetchAllData(findingFilters)
      .then((data) => {
        if (!cancelled) applyData(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unable to load dashboard");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [applyData, findingFilters]);

  useEffect(() => {
    if (selectedEvidence && evidenceRef.current) {
      evidenceRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [selectedEvidence]);

  async function handleSubmitDisputes() {
    setSubmittingDisputes(true);
    setWorkflowMessage(null);
    try {
      const submitted = await submitReadyDisputes();
      setWorkflowMessage(
        submitted.length
          ? `Submitted ${submitted.length} dispute${submitted.length === 1 ? "" : "s"}.`
          : "No approved or auto-eligible cases ready to submit.",
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to submit disputes");
    } finally {
      setSubmittingDisputes(false);
    }
  }

  async function handleCaseDecision(caseId: string, approve: boolean) {
    setDecidingCaseId(caseId);
    setWorkflowMessage(null);
    try {
      await decideCase(caseId, approve);
      setWorkflowMessage(approve ? "Case approved for submission." : "Case closed.");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update case");
    } finally {
      setDecidingCaseId(null);
    }
  }

  async function handleDeleteInvoice(invoiceId: string, invoiceNumber: string) {
    if (
      !window.confirm(
        `Delete invoice ${invoiceNumber} and all its findings and dispute cases? This cannot be undone.`,
      )
    ) {
      return;
    }
    setDeletingInvoiceId(invoiceId);
    setError(null);
    try {
      const removed = await deleteInvoice(invoiceId);
      setWorkflowMessage(
        `Removed ${invoiceNumber} (${removed.findings ?? 0} findings, ${removed.cases ?? 0} cases cleared).`,
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete invoice");
    } finally {
      setDeletingInvoiceId(null);
    }
  }

  async function handleClearRejectedRows() {
    if (!window.confirm("Clear all rejected upload rows for this workspace?")) return;
    setClearingRejected(true);
    try {
      await clearRejectedRows();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to clear rejected rows");
    } finally {
      setClearingRejected(false);
    }
  }

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.from(".dash-metric", {
          y: 14,
          duration: 0.4,
          stagger: 0.06,
          ease: "power2.out",
          delay: 0.15,
          clearProps: "transform",
        });
        gsap.from(".dash-panel", {
          y: 18,
          duration: 0.45,
          stagger: 0.08,
          ease: "power2.out",
          delay: 0.25,
          clearProps: "transform",
        });
      });

      return () => mm.revert();
    },
    { scope: containerRef },
  );

  const discrepancies = summary?.verdict_breakdown.find((row) => row.verdict === "DISCREPANCY");

  return (
    <div ref={containerRef} className="flex flex-col gap-6">
      <GlassCard variant="yellow" className="flex flex-col gap-4 p-6 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Operations Dashboard</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
            Fail-closed parcel invoice compiler — prove overbilling against effective-dated carrier rules
            and contracts, or refuse to act. Bring real data via{" "}
            <Link href="/upload" className="text-primary underline-offset-2 hover:underline">
              Upload & Audit
            </Link>
            , or see{" "}
            <Link href="/docs" className="text-primary underline-offset-2 hover:underline">
              Docs & Tutorial
            </Link>{" "}
            for the full explanation.
          </p>
        </div>
        <div className="flex gap-3">
          <Button variant="secondary" onClick={() => refresh()} disabled={loading}>
            <RefreshCw className={cn("mr-2 h-4 w-4", loading && "animate-spin")} />
            Refresh
          </Button>
          <Link
            href="/upload"
            className="inline-flex h-10 items-center justify-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-[0_0_20px_rgba(245,197,24,0.2)] transition hover:brightness-110"
          >
            <UploadCloud className="mr-2 h-4 w-4" />
            Upload & Audit
          </Link>
        </div>
      </GlassCard>

      {error ? (
        <GlassCard className="border-red-500/40 bg-red-500/10">
          <GlassCardContent className="flex items-center gap-3 pt-6 text-sm text-red-200">
            <AlertTriangle className="h-4 w-4" />
            {error}
          </GlassCardContent>
        </GlassCard>
      ) : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          className="dash-metric"
          title="Proven Discrepancies"
          value={String(discrepancies?.count ?? 0)}
          helper={`${money(discrepancies?.recoverable)} mathematically proven`}
        />
        <MetricCard
          className="dash-metric"
          title="Posted Recovery"
          value={money(summary?.posted_recovery)}
          helper={`${money(summary?.expected_recovery)} expected`}
        />
        <MetricCard
          className="dash-metric"
          title="Rejected Rows"
          value={String(summary?.rejected_rows ?? 0)}
          helper="Inputs that failed closed at ingestion"
        />
        <MetricCard
          className="dash-metric"
          title="Review Queue"
          value={String(summary?.cases_needing_review ?? 0)}
          helper={`${summary?.disputes_submitted ?? 0} submitted disputes`}
        />
      </section>

      {invoices.length ? (
        <GlassCard className="dash-panel">
          <GlassCardHeader>
            <GlassCardTitle>Your invoices</GlassCardTitle>
            <GlassCardDescription>
              Remove old test data here. Deleting an invoice also removes its charge lines, findings,
              and dispute cases.
            </GlassCardDescription>
          </GlassCardHeader>
          <GlassCardContent>
            <div className="divide-y divide-white/8 rounded-lg border border-white/10">
              {invoices.map((invoice) => (
                <div
                  key={invoice.id}
                  className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
                >
                  <div>
                    <div className="font-medium">
                      {invoice.carrier} {invoice.invoice_number}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {invoice.invoice_date} · {money(invoice.total_amount)}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    className="h-8 text-red-300 hover:bg-red-500/10 hover:text-red-200"
                    disabled={deletingInvoiceId !== null}
                    onClick={() => handleDeleteInvoice(invoice.id, invoice.invoice_number)}
                  >
                    {deletingInvoiceId === invoice.id ? (
                      <RefreshCw className="mr-2 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="mr-2 h-3.5 w-3.5" />
                    )}
                    Delete
                  </Button>
                </div>
              ))}
            </div>
          </GlassCardContent>
        </GlassCard>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[2fr_1fr]">
        <GlassCard className="dash-panel">
          <GlassCardHeader>
            <GlassCardTitle>Findings</GlassCardTitle>
            <GlassCardDescription>
              Filter by verdict, carrier, or invoice. Every line resolves to PASS, FAIL, DISCREPANCY,
              REVIEW, or NO CLAIM.
            </GlassCardDescription>
          </GlassCardHeader>
          <GlassCardContent>
            <div className="mb-4 flex flex-wrap items-end gap-3">
              <FilterSelect
                label="Verdict"
                value={findingFilters.verdict ?? ""}
                onChange={(verdict) =>
                  setFindingFilters((prev) => ({
                    ...prev,
                    verdict: verdict || undefined,
                  }))
                }
                options={[
                  ["", "All verdicts"],
                  ["DISCREPANCY", "Discrepancy"],
                  ["FAIL_MISSING_SOURCE", "Missing source"],
                  ["PASS", "Pass"],
                  ["REVIEW", "Review"],
                  ["NO_CLAIM", "No claim"],
                ]}
              />
              <FilterSelect
                label="Carrier"
                value={findingFilters.carrier ?? ""}
                onChange={(carrier) =>
                  setFindingFilters((prev) => ({
                    ...prev,
                    carrier: carrier || undefined,
                  }))
                }
                options={[
                  ["", "All carriers"],
                  ["UPS", "UPS"],
                  ["FEDEX", "FedEx"],
                  ["USPS", "USPS"],
                ]}
              />
              <FilterSelect
                label="Invoice"
                value={findingFilters.invoice_id ?? ""}
                onChange={(invoice_id) =>
                  setFindingFilters((prev) => ({
                    ...prev,
                    invoice_id: invoice_id || undefined,
                  }))
                }
                options={[
                  ["", "All invoices"],
                  ...invoices.map(
                    (inv) => [inv.id, `${inv.carrier} ${inv.invoice_number}`] as [string, string],
                  ),
                ]}
              />
              {(findingFilters.verdict || findingFilters.carrier || findingFilters.invoice_id) && (
                <Button
                  variant="ghost"
                  className="h-9 text-xs"
                  onClick={() => setFindingFilters({})}
                >
                  Clear filters
                </Button>
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-muted-foreground">
                  <tr className="border-b border-white/10">
                    <th className="py-3">Type</th>
                    <th>Verdict</th>
                    <th>Confidence</th>
                    <th>Billed</th>
                    <th>Claim</th>
                    <th>Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {findings.map((finding) => (
                    <tr key={finding.id} className="border-b border-white/5 last:border-b-0">
                      <td className="py-3">
                        <div className="font-medium">{finding.finding_type}</div>
                        <div className="max-w-md truncate text-xs text-muted-foreground">{finding.explanation}</div>
                      </td>
                      <td>
                        <VerdictBadge verdict={finding.verdict} />
                      </td>
                      <td className="text-xs">{finding.confidence_class}</td>
                      <td>{money(finding.billed_amount)}</td>
                      <td>{money(finding.recoverable_amount)}</td>
                      <td>
                        <Button
                          variant="ghost"
                          className="h-8 px-2"
                          onClick={() => setSelectedEvidence({ kind: "finding", finding })}
                        >
                          View
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!findings.length ? (
              <p className="mt-3 text-sm text-muted-foreground">No findings match the current filters.</p>
            ) : null}
          </GlassCardContent>
        </GlassCard>

        <div className="flex flex-col gap-6">
          <GlassCard className="dash-panel">
            <GlassCardHeader>
              <GlassCardTitle>Verdict Breakdown</GlassCardTitle>
              <GlassCardDescription>Audit outcomes across all checked lines.</GlassCardDescription>
            </GlassCardHeader>
            <GlassCardContent className="space-y-3">
              {(summary?.verdict_breakdown ?? []).map((row) => (
                <div key={row.verdict} className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.03] p-3">
                  <VerdictBadge verdict={row.verdict} />
                  <div className="text-right">
                    <div className="text-sm font-medium">{row.count}</div>
                    <div className="text-xs text-muted-foreground">{money(row.recoverable)}</div>
                  </div>
                </div>
              ))}
              {!summary?.verdict_breakdown?.length ? (
                <p className="text-sm text-muted-foreground">Upload invoices and run an audit to populate verdicts.</p>
              ) : null}
            </GlassCardContent>
          </GlassCard>

          <GlassCard className="dash-panel">
            <GlassCardHeader>
              <GlassCardTitle>Claim Mix</GlassCardTitle>
              <GlassCardDescription>Proven discrepancies by charge class.</GlassCardDescription>
            </GlassCardHeader>
            <GlassCardContent className="space-y-3">
              {(summary?.surcharge_mix ?? []).map((row) => (
                <div key={row.type} className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.03] p-3">
                  <div>
                    <div className="text-sm font-medium">{row.type}</div>
                    <div className="text-xs text-muted-foreground">{row.count} findings</div>
                  </div>
                  <Badge>{money(row.recoverable)}</Badge>
                </div>
              ))}
              {!summary?.surcharge_mix?.length ? (
                <p className="text-sm text-muted-foreground">No proven claims yet.</p>
              ) : null}
            </GlassCardContent>
          </GlassCard>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <GlassCard className="dash-panel">
          <GlassCardHeader>
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <ShieldX className="h-4 w-4 text-red-300" />
                  <GlassCardTitle>Rejected Rows</GlassCardTitle>
                </div>
                <GlassCardDescription>
                  Inputs that failed required-field, format, or reconciliation gates. Nothing here was guessed at.
                </GlassCardDescription>
              </div>
              {rejectedRows.length ? (
                <Button
                  variant="secondary"
                  className="h-8 shrink-0 text-xs"
                  disabled={clearingRejected}
                  onClick={handleClearRejectedRows}
                >
                  Clear all
                </Button>
              ) : null}
            </div>
          </GlassCardHeader>
          <GlassCardContent className="space-y-3">
            {rejectedRows.slice(0, 8).map((row) => (
              <div key={row.id} className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium">
                    {row.ingest_stage}
                    {row.row_index !== null ? ` row ${row.row_index}` : ""}
                  </span>
                  <Badge variant="destructive">REJECTED</Badge>
                </div>
                <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                  {row.failure_reasons.map((reason, idx) => (
                    <li key={idx}>{reason}</li>
                  ))}
                </ul>
              </div>
            ))}
            {!rejectedRows.length ? <p className="text-sm text-muted-foreground">No rejected rows.</p> : null}
          </GlassCardContent>
        </GlassCard>

        <GlassCard className="dash-panel">
          <GlassCardHeader>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <GlassCardTitle>Dispute Cases</GlassCardTitle>
                <GlassCardDescription>
                  Approve cases for submission, then submit ready disputes from the action below.
                </GlassCardDescription>
              </div>
              <Button
                variant="secondary"
                className="h-8 shrink-0 text-xs"
                disabled={submittingDisputes || !cases.length}
                onClick={handleSubmitDisputes}
              >
                {submittingDisputes ? (
                  <RefreshCw className="mr-2 h-3.5 w-3.5 animate-spin" />
                ) : null}
                Submit ready disputes
              </Button>
            </div>
          </GlassCardHeader>
          <GlassCardContent className="space-y-3">
            {workflowMessage ? (
              <p className="rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-xs text-primary">
                {workflowMessage}
              </p>
            ) : null}
            {cases.slice(0, 8).map((item) => {
              const reviewable =
                item.status === "NEEDS_REVIEW" || item.status === "READY_FOR_AUTO_DISPUTE";
              return (
                <div key={item.id} className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="min-w-0 truncate text-sm font-medium">{item.title}</span>
                    <StatusBadge status={item.status} />
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Deadline: {item.dispute_deadline ?? "n/a"}
                    {item.auto_dispute_eligible ? " · auto-eligible" : ""}
                  </div>
                  <div className="mt-2 flex flex-wrap items-center justify-end gap-1">
                    {reviewable ? (
                      <>
                        <Button
                          variant="ghost"
                          className="h-7 px-2 text-xs text-emerald-300"
                          disabled={decidingCaseId !== null}
                          onClick={() => handleCaseDecision(item.id, true)}
                        >
                          Approve
                        </Button>
                        <Button
                          variant="ghost"
                          className="h-7 px-2 text-xs text-red-300"
                          disabled={decidingCaseId !== null}
                          onClick={() => handleCaseDecision(item.id, false)}
                        >
                          Reject
                        </Button>
                      </>
                    ) : null}
                    <Button
                      variant="ghost"
                      className="h-7 px-2 text-xs"
                      onClick={() => setSelectedEvidence({ kind: "case", item })}
                    >
                      View evidence
                    </Button>
                  </div>
                </div>
              );
            })}
            {!cases.length ? (
              <p className="text-sm text-muted-foreground">
                No cases yet.{" "}
                <Link href="/upload" className="text-primary underline-offset-2 hover:underline">
                  Build cases on Upload & Audit
                </Link>
                .
              </p>
            ) : null}
          </GlassCardContent>
        </GlassCard>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <QueueCard
          className="dash-panel"
          title="Disputes"
          items={disputes}
          getStatus={(item) => item.status}
          getTitle={(item) => `${item.carrier} ${item.external_reference ?? item.id} (${item.submission_channel})`}
        />
        <QueueCard
          className="dash-panel"
          title="Refund Ledger"
          items={refunds}
          getStatus={(item) => item.status}
          getTitle={(item) => `${item.tracking_number} ${money(item.posted_credit ?? item.expected_credit)}`}
        />
      </section>

      {selectedEvidence ? (
        <div ref={evidenceRef}>
          <EvidenceViewer selection={selectedEvidence} onClose={() => setSelectedEvidence(null)} />
        </div>
      ) : null}
    </div>
  );
}

function MetricCard({
  title,
  value,
  helper,
  className,
}: {
  title: string;
  value: string;
  helper: string;
  className?: string;
}) {
  return (
    <GlassCard className={className}>
      <GlassCardHeader className="pb-3">
        <GlassCardDescription>{title}</GlassCardDescription>
        <GlassCardTitle className="text-3xl text-primary">{value}</GlassCardTitle>
      </GlassCardHeader>
      <GlassCardContent>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <CheckCircle2 className="h-3.5 w-3.5 text-primary/80" />
          {helper}
        </div>
      </GlassCardContent>
    </GlassCard>
  );
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const variant =
    verdict === "DISCREPANCY"
      ? "destructive"
      : verdict === "PASS" || verdict === "NO_CLAIM"
        ? "success"
        : verdict === "REVIEW"
          ? "warning"
          : "secondary";
  return <Badge variant={variant}>{verdict.replace(/_/g, " ")}</Badge>;
}

function StatusBadge({ status }: { status: string }) {
  const variant =
    status.includes("WON") || status.includes("MATCHED") || status.includes("APPROVED")
      ? "success"
      : status.includes("REVIEW")
        ? "warning"
        : "secondary";
  return <Badge variant={variant}>{status}</Badge>;
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: ReadonlyArray<readonly [string, string]>;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-muted-foreground">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 min-w-[10rem] rounded-lg border border-white/10 bg-black/30 px-3 text-sm text-foreground"
      >
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue || "all"} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  );
}

function QueueCard<T>({
  title,
  items,
  getStatus,
  getTitle,
  className,
}: {
  title: string;
  items: T[];
  getStatus: (item: T) => string;
  getTitle: (item: T) => string;
  className?: string;
}) {
  return (
    <GlassCard className={className}>
      <GlassCardHeader>
        <GlassCardTitle>{title}</GlassCardTitle>
        <GlassCardDescription>{items.length} records</GlassCardDescription>
      </GlassCardHeader>
      <GlassCardContent className="space-y-3">
        {items.slice(0, 8).map((item, index) => (
          <div
            key={`${title}-${index}`}
            className="flex items-center justify-between gap-3 rounded-lg border border-white/10 bg-white/[0.03] p-3"
          >
            <div className="min-w-0 truncate text-sm">{getTitle(item)}</div>
            <StatusBadge status={getStatus(item)} />
          </div>
        ))}
        {!items.length ? <p className="text-sm text-muted-foreground">No records yet.</p> : null}
      </GlassCardContent>
    </GlassCard>
  );
}
