from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CarrierCode, Case, CaseStatus, Dispute, DisputeStatus, FindingStatus


@dataclass(frozen=True)
class DisputeSubmission:
    status: DisputeStatus
    channel: str
    external_reference: str | None
    request_payload: dict
    response_payload: dict


class CarrierDisputeAdapter(Protocol):
    carrier: CarrierCode

    def submit(self, case: Case) -> DisputeSubmission:
        ...


class HumanInLoopAdapter:
    def __init__(self, carrier: CarrierCode) -> None:
        self.carrier = carrier

    def submit(self, case: Case) -> DisputeSubmission:
        reference = f"TASK-{case.id[:8].upper()}"
        return DisputeSubmission(
            status=DisputeStatus.SUBMITTED,
            channel="human_in_loop",
            external_reference=reference,
            request_payload={
                "task_type": "billing_portal_submission",
                "carrier": self.carrier.value,
                "case_id": case.id,
                "evidence_packet": case.evidence_packet,
                "evidence_document": case.evidence_document,
                "dispute_deadline": str(case.dispute_deadline) if case.dispute_deadline else None,
            },
            response_payload={
                "message": "Human review task created with carrier-ready evidence packet.",
                "reference": reference,
            },
        )


class USPSDisputeApiAdapter:
    carrier = CarrierCode.USPS

    def submit(self, case: Case) -> DisputeSubmission:
        reference = f"USPS-SANDBOX-{case.id[:8].upper()}"
        return DisputeSubmission(
            status=DisputeStatus.SUBMITTED,
            channel="api",
            external_reference=reference,
            request_payload={
                "caseId": case.id,
                "evidence": case.evidence_packet,
                "evidence_document": case.evidence_document,
                "dispute_deadline": str(case.dispute_deadline) if case.dispute_deadline else None,
                "sandbox": True,
            },
            response_payload={
                "status": "accepted",
                "reference": reference,
                "note": "Replace with USPS Adjustments/Disputes API credentials for live submission.",
            },
        )


class DisputeOrchestrator:
    def __init__(self, db: Session) -> None:
        self.db = db

    def adapter_for(self, carrier: CarrierCode) -> CarrierDisputeAdapter:
        if carrier == CarrierCode.USPS:
            return USPSDisputeApiAdapter()
        return HumanInLoopAdapter(carrier)

    def submit_ready_cases(self, tenant_id: str) -> list[Dispute]:
        cases = list(
            self.db.scalars(
                select(Case).where(
                    Case.tenant_id == tenant_id,
                    Case.status.in_([CaseStatus.READY_FOR_AUTO_DISPUTE, CaseStatus.APPROVED]),
                )
            )
        )
        disputes: list[Dispute] = []
        for case in cases:
            if self.db.scalar(select(Dispute).where(Dispute.case_id == case.id)):
                continue
            carrier = case.finding.invoice_line.invoice.carrier
            # Defensive guard: only USPS has a public dispute API. FedEx/UPS
            # cases must come through explicit human approval, never auto.
            if case.status == CaseStatus.READY_FOR_AUTO_DISPUTE and carrier != CarrierCode.USPS:
                case.status = CaseStatus.NEEDS_REVIEW
                continue
            submission = self.adapter_for(carrier).submit(case)
            dispute = Dispute(
                tenant_id=tenant_id,
                case_id=case.id,
                carrier=carrier,
                status=submission.status,
                submission_channel=submission.channel,
                external_reference=submission.external_reference,
                request_payload=submission.request_payload,
                response_payload=submission.response_payload,
                submitted_at=datetime.now(UTC),
            )
            self.db.add(dispute)
            case.status = CaseStatus.SUBMITTED
            case.finding.status = FindingStatus.DISPUTED
            disputes.append(dispute)
        self.db.commit()
        return disputes

    def approve_case(self, case_id: str, approve: bool, notes: str | None = None) -> Case:
        case = self.db.get(Case, case_id)
        if not case:
            raise ValueError(f"case not found: {case_id}")
        case.reviewer_notes = notes
        case.status = CaseStatus.APPROVED if approve else CaseStatus.CLOSED
        self.db.commit()
        self.db.refresh(case)
        return case
