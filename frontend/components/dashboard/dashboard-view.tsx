"use client";

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, CheckCircle2, RefreshCw, ShieldX, UploadCloud } from "lucide-react";

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
  fetchCases,
  fetchDashboard,
  fetchDisputes,
  fetchFindings,
  fetchRefunds,
  fetchRejectedRows,
  Finding,
  Refund,
  RejectedRow,
  type DashboardSummary,
} from "@/lib/api";
import { money } from "@/lib/utils";

type EvidenceView =
  | { kind: "json"; data: Record<string, unknown> }
  | { kind: "document"; text: string };

async function fetchAllData() {
  const [summary, findings, cases, disputes, refunds, rejectedRows] = await Promise.all([
    fetchDashboard(),
    fetchFindings(),
    fetchCases(),
    fetchDisputes(),
    fetchRefunds(),
    fetchRejectedRows(),
  ]);
  return { summary, findings, cases, disputes, refunds, rejectedRows };
}

export function DashboardView() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [cases, setCases] = useState<Case[]>([]);
  const [disputes, setDisputes] = useState<Dispute[]>([]);
  const [refunds, setRefunds] = useState<Refund[]>([]);
  const [rejectedRows, setRejectedRows] = useState<RejectedRow[]>([]);
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const applyData = useCallback((data: Awaited<ReturnType<typeof fetchAllData>>) => {
    setSummary(data.summary);
    setFindings(data.findings);
    setCases(data.cases);
    setDisputes(data.disputes);
    setRefunds(data.refunds);
    setRejectedRows(data.rejectedRows);
  }, []);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      applyData(await fetchAllData());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load dashboard");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    fetchAllData()
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
  }, [applyData]);

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
            <a href="/upload" className="text-primary underline-offset-2 hover:underline">
              Upload & Audit
            </a>
            , or see{" "}
            <a href="/docs" className="text-primary underline-offset-2 hover:underline">
              Docs & Tutorial
            </a>{" "}
            for the full explanation.
          </p>
        </div>
        <div className="flex gap-3">
          <Button variant="secondary" onClick={refresh} disabled={loading}>
            <RefreshCw className="mr-2 h-4 w-4" />
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

      <section className="grid gap-6 xl:grid-cols-[2fr_1fr]">
        <GlassCard className="dash-panel">
          <GlassCardHeader>
            <GlassCardTitle>Latest Findings</GlassCardTitle>
            <GlassCardDescription>
              Every line resolves to PASS, FAIL (missing source), DISCREPANCY, REVIEW, or NO CLAIM.
            </GlassCardDescription>
          </GlassCardHeader>
          <GlassCardContent>
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
                  {findings.slice(0, 14).map((finding) => (
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
                          onClick={() => setSelectedEvidence({ kind: "json", data: finding.evidence })}
                        >
                          View
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
            <div className="flex items-center gap-2">
              <ShieldX className="h-4 w-4 text-red-300" />
              <GlassCardTitle>Rejected Rows</GlassCardTitle>
            </div>
            <GlassCardDescription>
              Inputs that failed required-field, format, or reconciliation gates. Nothing here was guessed at.
            </GlassCardDescription>
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
            <GlassCardTitle>Dispute Cases</GlassCardTitle>
            <GlassCardDescription>Built from proven discrepancies only, with filing deadlines.</GlassCardDescription>
          </GlassCardHeader>
          <GlassCardContent className="space-y-3">
            {cases.slice(0, 8).map((item) => (
              <div key={item.id} className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="min-w-0 truncate text-sm font-medium">{item.title}</span>
                  <StatusBadge status={item.status} />
                </div>
                <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                  <span>Deadline: {item.dispute_deadline ?? "n/a"}</span>
                  {item.evidence_document ? (
                    <Button
                      variant="ghost"
                      className="h-7 px-2 text-xs"
                      onClick={() =>
                        setSelectedEvidence({ kind: "document", text: item.evidence_document ?? "" })
                      }
                    >
                      Evidence packet
                    </Button>
                  ) : null}
                </div>
              </div>
            ))}
            {!cases.length ? <p className="text-sm text-muted-foreground">No cases yet.</p> : null}
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
        <GlassCard className="dash-panel">
          <GlassCardHeader>
            <div className="flex items-center justify-between">
              <div>
                <GlassCardTitle>
                  {selectedEvidence.kind === "document" ? "Dispute Evidence Document" : "Evidence Packet"}
                </GlassCardTitle>
                <GlassCardDescription>
                  Versioned, hash-identified dispute support data for the selected item.
                </GlassCardDescription>
              </div>
              <Button variant="secondary" onClick={() => setSelectedEvidence(null)}>
                Close
              </Button>
            </div>
          </GlassCardHeader>
          <GlassCardContent>
            <pre className="max-h-96 overflow-auto rounded-lg border border-white/10 bg-black/40 p-4 text-xs text-zinc-200">
              {selectedEvidence.kind === "document"
                ? selectedEvidence.text
                : JSON.stringify(selectedEvidence.data, null, 2)}
            </pre>
          </GlassCardContent>
        </GlassCard>
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
