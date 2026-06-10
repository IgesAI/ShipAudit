from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditVerdict,
    CarrierCode,
    Case,
    CaseStatus,
    ConfidenceClass,
    Finding,
    FindingStatus,
)
from app.services.rule_repository import RuleRepository

DEFAULT_DEADLINE_DAYS = 180

EVIDENCE_TEMPLATE = """CARRIER BILLING DISPUTE — {carrier}
================================================================
Invoice:            {invoice_number}
Invoice date:       {invoice_date}
Account:            {account_number}
Tracking:           {tracking_number}
Charge code:        {charge_code} ({charge_type})
Ship date:          {ship_date}
Billed amount:      ${billed_amount}
Expected amount:    ${expected_amount}
Claim amount:       ${claim_amount}
Dispute deadline:   {deadline}

FINDING
{explanation}

RULE / CONTRACT SOURCE
Rule version:       {rule_version}
Source file:        {rule_source}
Source hash:        {rule_hash}

SOURCE DOCUMENT PROVENANCE
Invoice file hash:  {invoice_hash}
Line provenance:    {line_provenance}
Manifest:           {manifest}

This claim is based exclusively on exact, effective-dated carrier rules,
contract terms, and the shipper's original manifest records. All source
documents are preserved immutably and identified by SHA-256 hash.
"""


class CaseBuilder:
    """Builds dispute cases exclusively from proven DISCREPANCY findings.

    REVIEW, FAIL_MISSING_SOURCE, NO_CLAIM, and PASS verdicts never become
    cases. Auto-dispute eligibility additionally requires PROVEN confidence
    class; STRONG (e.g. validator-consensus residential) goes to human review.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.rules = RuleRepository(db)

    def build_cases_for_tenant(self, tenant_id: str) -> list[Case]:
        findings = list(
            self.db.scalars(
                select(Finding).where(
                    Finding.tenant_id == tenant_id,
                    Finding.status == FindingStatus.OPEN,
                    Finding.verdict == AuditVerdict.DISCREPANCY,
                    Finding.recoverable_amount > Decimal("0.00"),
                )
            )
        )
        cases: list[Case] = []
        for finding in findings:
            existing = self.db.scalar(select(Case).where(Case.finding_id == finding.id))
            if existing:
                continue
            case = self.build_case(finding)
            self.db.add(case)
            finding.status = FindingStatus.CASED
            cases.append(case)
        self.db.commit()
        return cases

    def build_case(self, finding: Finding) -> Case:
        line = finding.invoice_line
        invoice = line.invoice
        shipment = line.shipment

        deadline_days = DEFAULT_DEADLINE_DAYS
        policy = self.rules.dispute_policy(invoice.carrier, invoice.invoice_date)
        if policy:
            deadline_days = int(policy.payload.get("deadline_days", DEFAULT_DEADLINE_DAYS))
        deadline = invoice.invoice_date + timedelta(days=deadline_days)

        # FedEx/UPS submissions always require human approval; only carriers with
        # a public dispute API (USPS) may auto-submit, and only on PROVEN math.
        api_channel = bool(policy and policy.payload.get("auto_dispute_channel") == "api")
        proven = finding.confidence_class == ConfidenceClass.PROVEN
        auto_eligible = proven and api_channel and invoice.carrier == CarrierCode.USPS
        status = CaseStatus.READY_FOR_AUTO_DISPUTE if auto_eligible else CaseStatus.NEEDS_REVIEW

        title = f"{finding.finding_type.value} dispute for {line.tracking_number}"
        summary = (
            f"{invoice.carrier.value} invoice {invoice.invoice_number} billed "
            f"{finding.billed_amount}; expected {finding.expected_amount}; "
            f"claim {finding.recoverable_amount}. {finding.explanation}"
        )
        evidence_packet = {
            "finding_id": finding.id,
            "verdict": finding.verdict.value,
            "confidence_class": finding.confidence_class.value,
            "invoice": {
                "id": invoice.id,
                "number": invoice.invoice_number,
                "date": str(invoice.invoice_date),
                "carrier": invoice.carrier.value,
                "account_number": invoice.account_number,
                "source_file_hash": invoice.source_file_hash,
            },
            "line": {
                "id": line.id,
                "tracking_number": line.tracking_number,
                "service_code": line.service_code,
                "ship_date": str(line.ship_date),
                "charge_code": line.charge_code,
                "charge_type": line.charge_type.value,
                "amount": str(line.amount),
                "provenance": line.provenance,
            },
            "shipment": {
                "id": shipment.id if shipment else None,
                "manifest_service_code": shipment.service_code if shipment else None,
            },
            "rule_version_id": finding.rule_version_id,
            "claim_amount": str(finding.recoverable_amount),
            "dispute_deadline": str(deadline),
            "evidence": finding.evidence,
            "submission_policy": {
                "channel": "api" if auto_eligible else "human_in_loop",
                "requires_human_approval": not auto_eligible,
                "confidence_class": finding.confidence_class.value,
            },
        }
        return Case(
            tenant_id=finding.tenant_id,
            finding_id=finding.id,
            status=status,
            auto_dispute_eligible=auto_eligible,
            dispute_deadline=deadline,
            title=title,
            summary=summary,
            evidence_packet=evidence_packet,
            evidence_document=self.render_evidence_document(finding, deadline),
        )

    def render_evidence_document(self, finding: Finding, deadline) -> str:
        line = finding.invoice_line
        invoice = line.invoice
        shipment = line.shipment
        evidence = finding.evidence or {}
        return EVIDENCE_TEMPLATE.format(
            carrier=invoice.carrier.value,
            invoice_number=invoice.invoice_number,
            invoice_date=invoice.invoice_date,
            account_number=invoice.account_number,
            tracking_number=line.tracking_number,
            charge_code=line.charge_code,
            charge_type=line.charge_type.value,
            ship_date=line.ship_date,
            billed_amount=finding.billed_amount,
            expected_amount=finding.expected_amount if finding.expected_amount is not None else "n/a",
            claim_amount=finding.recoverable_amount,
            deadline=deadline,
            explanation=finding.explanation,
            rule_version=evidence.get("rule_version_id") or finding.rule_version_id or "n/a",
            rule_source=evidence.get("rule_source_uri") or evidence.get("rate_card_name") or "n/a",
            rule_hash=evidence.get("rule_source_hash") or evidence.get("rate_card_hash") or "n/a",
            invoice_hash=invoice.source_file_hash or "n/a",
            line_provenance=line.provenance,
            manifest=(
                {
                    "shipment_id": shipment.id,
                    "service": shipment.service_code,
                    "ship_date": str(shipment.ship_date),
                }
                if shipment
                else "n/a"
            ),
        )
